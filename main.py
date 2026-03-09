"""
QA Agent V2 - Bot Slack intelligent avec intégration Jira
Version avec confirmation avant création + iOS/Android dynamique
"""
import os
import re
import requests
from typing import Dict
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from conversation_manager import ConversationManager
from classifier import classify_intent
from ticket import generate_ticket_with_history
from testplan import generate_testplan_with_history
from jira_client import JiraClient
from jira_ai_helper import fill_jira_fields_with_ai

from prd_parser import is_notion_url, extract_notion_url, fetch_notion_content, extract_pdf_content
from testplan_generator import generate_testplan_from_prd



load_dotenv()

# Initialiser l'app Slack
app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET")
)

# Gestionnaire de conversations
conv_manager = ConversationManager(session_timeout_minutes=30)

# Client Jira
try:
    jira_client = JiraClient()
    jira_enabled = True
    print("✅ Jira integration enabled")
except Exception as e:
    jira_client = None
    jira_enabled = False
    print(f"⚠️  Jira integration disabled: {e}")

def detect_platform(message: str) -> str:
    """
    Détecte la plateforme (iOS ou Android) dans un message.
    
    Returns:
        "ios", "android", ou "unknown"
    """
    message_lower = message.lower()
    
    # Patterns iOS
    ios_keywords = ["ios", "iphone", "ipad", "ipod", "apple", "xcode"]
    android_keywords = ["android", "pixel", "samsung", "oneplus", "xiaomi"]
    
    has_ios = any(keyword in message_lower for keyword in ios_keywords)
    has_android = any(keyword in message_lower for keyword in android_keywords)
    
    if has_ios and not has_android:
        return "ios"
    elif has_android and not has_ios:
        return "android"
    else:
        return "unknown"

@app.event("message")
def handle_message(event, say):
    """
    Gère tous les messages avec personnalité et questions intelligentes.
    """
    # Ignorer les messages du bot
    if event.get("bot_id"):
        return
    
    # Ignorer les threads
    if event.get("thread_ts"):
        return
    
    user_id = event.get("user")
    user_message = event.get("text", "").strip()
    
    if not user_message:
        return
    
    # NOUVEAU : Détecter les liens Notion pour PRD
    if is_notion_url(user_message):
        notion_url = extract_notion_url(user_message)
        if notion_url:
            say("📄 Lien Notion détecté ! Je récupère le PRD et génère un plan de test...")
            
            try:
                # Fetch le contenu Notion
                prd_content = fetch_notion_content(notion_url)
                
                # Générer le plan de test
                testplan = generate_testplan_from_prd(
                    prd_content,
                    prd_source=f"Notion: {notion_url}"
                )
                
                # Envoyer le plan de test
                say(testplan)
                return
                
            except Exception as e:
                say(f"❌ Erreur lors de la récupération du PRD Notion : {str(e)}")
                return
    
    # Commandes spéciales
    if user_message.lower() == "reset":
        handle_reset_command(user_id, say)
        return
    
    # Récupérer le contexte actuel
    context = conv_manager.get_context(user_id)
    history = conv_manager.get_history(user_id)
    
    # Déterminer si c'est une nouvelle demande ou une continuation
    is_continuation = len(history) > 0 and context.get("mode") is not None
    
    try:
        if is_continuation:
            # Continuation de conversation
            conv_manager.add_message(user_id, "user", user_message)
            full_history = conv_manager.get_history(user_id)
            
            # Générer avec le contexte complet
            if context["mode"] == "ticket":
                result = generate_ticket_with_history(full_history)
            else:
                result = generate_testplan_with_history(full_history)
            
            # Ajouter la réponse à l'historique
            conv_manager.add_message(user_id, "assistant", result)
            
            say(result)
            
            # Si c'est un ticket et Jira est activé, proposer de créer dans Jira
            if context["mode"] == "ticket" and jira_enabled and is_ticket_complete(result):
                show_jira_creation_button(say, user_id, result)
            
        else:
            # Nouvelle conversation
            intent = classify_intent(user_message)
            
            # Ne pas clear si on a des attachments en attente
            has_attachments = context.get("attachments") and len(context.get("attachments", [])) > 0
            
            if not has_attachments:
                conv_manager.clear_conversation(user_id)
            else:
                # Juste ajouter le message sans effacer le contexte
                print(f"📎 Attachments détectés ({len(context['attachments'])}), on garde le contexte")
            
            conv_manager.add_message(user_id, "user", user_message)
            
            if intent == "ticket":
                conv_manager.update_context(user_id, mode="ticket")
                history = conv_manager.get_history(user_id)
                result = generate_ticket_with_history(history)
                conv_manager.add_message(user_id, "assistant", result)
                
                say(result)
                
                # Proposer création Jira si ticket complet
                if jira_enabled and is_ticket_complete(result):
                    show_jira_creation_button(say, user_id, result)
                
            elif intent == "testplan":
                conv_manager.update_context(user_id, mode="testplan")
                history = conv_manager.get_history(user_id)
                result = generate_testplan_with_history(history)
                conv_manager.add_message(user_id, "assistant", result)
                
                say(result)
                
            else:
                say("Hmm, je ne suis pas sûr de comprendre. Tu veux créer un ticket de bug ou un plan de test ?")
                
    except Exception as e:
        say(f"Oups, j'ai rencontré une erreur : {str(e)}")
        print(f"Erreur: {e}")
        conv_manager.clear_conversation(user_id)

def is_ticket_complete(ticket_text: str) -> bool:
    """
    Vérifie si le ticket semble complet (a un titre et une description).
    """
    has_title = "*Title:*" in ticket_text or "Title:" in ticket_text
    has_behavior = "*Current behavior*" in ticket_text or "Current behavior" in ticket_text
    has_repro = "*How to reproduce*" in ticket_text or "How to reproduce" in ticket_text
    
    return has_title and has_behavior and has_repro

def show_jira_creation_button(say, user_id: str, ticket_content: str):
    """
    Affiche un bouton pour créer le ticket dans Jira.
    """
    conv_manager.update_context(user_id, current_ticket=ticket_content)
    
    say(
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ Ticket prêt ! Tu veux le créer dans Jira ?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📤 Créer dans Jira"
                        },
                        "style": "primary",
                        "action_id": "create_jira_ticket"
                    }
                ]
            }
        ],
        text="Ticket prêt pour Jira"
    )

@app.action("create_jira_ticket")
def handle_create_jira_ticket(ack, body, say):
    """
    Analyse le ticket et prépare les données Jira.
    """
    ack()
    
    user_id = body["user"]["id"]
    context = conv_manager.get_context(user_id)
    
    if "current_ticket" not in context:
        say("❌ Pas de ticket en attente. Crée d'abord un ticket.")
        return
    
    say("🔍 Analyse du ticket pour Jira...")
    
    try:
        ticket_content = context["current_ticket"]
        
        # Parser le ticket
        ticket_data = parse_ticket_for_jira(ticket_content)
        
        if not ticket_data:
            say("❌ Impossible de parser le ticket. Vérifie le format.")
            return
        
        # Récupérer les métadonnées Jira
        jira_metadata = jira_client.parse_metadata_for_ai()
        
        # Utiliser l'AI pour remplir les champs
        ai_fields = fill_jira_fields_with_ai(ticket_content, jira_metadata)
        
        # Sauvegarder dans le contexte
        jira_ready = {
            "title": ticket_data["title"],
            "description": ticket_data["description"],
            "priority_id": ai_fields["priority_id"],
            "medical_status_id": ai_fields["medical_status_id"],
            "impact_team_ids": ai_fields["impact_team_ids"],
            "component_ids": ai_fields.get("component_ids", []),
            "labels": ai_fields["labels"]
        }
        
        conv_manager.update_context(user_id, jira_ready=jira_ready)
        
        # Afficher la preview
        priority_name = get_priority_name(ai_fields["priority_id"], jira_metadata)
        medical_status_name = get_medical_status_name(ai_fields["medical_status_id"], jira_metadata)
        impact_team_names = get_impact_team_names(ai_fields["impact_team_ids"], jira_metadata)
        component_names = get_component_names(ai_fields.get("component_ids", []), jira_metadata)
        
        show_jira_confirmation(
            say, 
            user_id,
            ticket_data["title"],
            priority_name,
            medical_status_name,
            impact_team_names,
            component_names,
            ai_fields["labels"],
            ai_fields["reasoning"]
        )
        
    except Exception as e:
        say(f"❌ Erreur lors de l'analyse : {str(e)}")
        print(f"Jira analysis error: {e}")
        import traceback
        traceback.print_exc()

def show_jira_confirmation(say, user_id: str, title: str, priority: str, medical_status: str, impact_teams: list, components: list, labels: list, reasoning: str):
    """
    Affiche une preview du ticket Jira avec demande de confirmation.
    """
    components_str = ", ".join(components) if components else "Aucun"
    impact_teams_str = ", ".join(impact_teams) if impact_teams else "Aucun"
    labels_str = ", ".join(labels) if labels else "Aucun"

    # Récupérer les attachments du contexte
    context = conv_manager.get_context(user_id)
    attachments = context.get("attachments", [])
    attachments_str = ""
    
    if attachments:
        attachments_list = [f"• {att['filename']}" for att in attachments]
        attachments_str = f"\n*Attachments :* {len(attachments)} fichier(s)\n" + "\n".join(attachments_list)
    
    # Détecter la plateforme depuis le ticket
    ticket_content = context.get("jira_ready", {}).get("description", "")
    platform = detect_platform(ticket_content)
    
    # Si plateforme détectée, stocker dans le contexte
    if platform in ["ios", "android"]:
        conv_manager.update_context(user_id, platform=platform)
        platform_emoji = "🍎" if platform == "ios" else "🤖"
        platform_name = "HMIOS" if platform == "ios" else "HMANDROID"
        platform_str = f"\n*Plateforme :* {platform_emoji} {platform_name}"
    else:
        platform_str = "\n*Plateforme :* ❓ À choisir ci-dessous"
    
    # Construire les boutons de plateforme (SANS None pour le style)
    ios_button = {
        "type": "button",
        "text": {"type": "plain_text", "text": "🍎 iOS (HMIOS)"},
        "action_id": "select_ios"
    }
    android_button = {
        "type": "button",
        "text": {"type": "plain_text", "text": "🤖 Android (HMANDROID)"},
        "action_id": "select_android"
    }
    
    # Ajouter le style seulement si la plateforme est sélectionnée
    if platform == "ios":
        ios_button["style"] = "primary"
    if platform == "android":
        android_button["style"] = "primary"
    
    platform_buttons = [ios_button, android_button]
    
    say(
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📋 Preview du ticket Jira*\n\n*Titre :* {title}\n*Priority :* {priority}\n*Medical Status :* {medical_status}\n*Impact Teams :* {impact_teams_str}\n*Components :* {components_str}\n*Labels :* {labels_str}, sqa{attachments_str}{platform_str}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"💡 _{reasoning}_"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📱 *Choisis la plateforme:*"
                }
            },
            {
                "type": "actions",
                "elements": platform_buttons
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Tu confirmes la création ?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Oui, créer maintenant"
                        },
                        "style": "primary",
                        "value": "confirm",
                        "action_id": "confirm_jira_creation"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "❌ Annuler"
                        },
                        "style": "danger",
                        "value": "cancel",
                        "action_id": "cancel_jira_creation"
                    }
                ]
            }
        ],
        text=f"Confirmer création Jira : {title}"
    )

@app.action("select_ios")
def handle_select_ios(ack, body, say):
    """Sélectionne iOS comme plateforme"""
    ack()
    user_id = body["user"]["id"]
    
    # Mettre à jour le contexte
    conv_manager.update_context(user_id, platform="ios")
    
    say("✅ Plateforme iOS sélectionnée → Ticket sera créé dans *HMIOS*")

@app.action("select_android")
def handle_select_android(ack, body, say):
    """Sélectionne Android comme plateforme"""
    ack()
    user_id = body["user"]["id"]
    
    # Mettre à jour le contexte
    conv_manager.update_context(user_id, platform="android")
    
    say("✅ Plateforme Android sélectionnée → Ticket sera créé dans *HMANDROID*")

@app.action("confirm_jira_creation")
def handle_confirm_creation(ack, body, say):
    """
    Crée effectivement le ticket dans Jira après confirmation.
    """
    ack()
    
    user_id = body["user"]["id"]
    context = conv_manager.get_context(user_id)
    
    if "jira_ready" not in context:
        say("❌ Données du ticket perdues. Recommence s'il te plaît.")
        return
    
    say("⏳ Création dans Jira...")
    
    try:
        jira_data = context["jira_ready"]
        platform = context.get("platform", "ios")  # Default iOS
        
        # NOUVEAU : Utiliser le bon client Jira selon la plateforme
        if platform == "android":
            # Créer un client avec HMANDROID
            android_client = JiraClient()
            android_client.project_key = "HMANDROID"
            current_jira_client = android_client
            project_name = "HMANDROID"
        else:
            # Utiliser le client par défaut (HMIOS)
            current_jira_client = jira_client
            project_name = os.getenv("JIRA_PROJECT_KEY", "HMIOS")
        
        # Préparer les attachments si présents
        attachments_to_upload = []
        
        if "attachments" in context and context["attachments"]:
            say(f"📎 Téléchargement de {len(context['attachments'])} fichier(s)...")
            
            for attachment_info in context["attachments"]:
                try:
                    # Télécharger le fichier depuis Slack
                    file_url = attachment_info["url"]
                    headers = {"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
                    response = requests.get(file_url, headers=headers)
                    
                    if response.status_code == 200:
                        file_size_mb = len(response.content) / (1024 * 1024)
                        print(f"📥 Fichier téléchargé : {attachment_info['filename']} ({file_size_mb:.2f} MB)")
                        
                        # Limiter à 10MB
                        if file_size_mb > 10:
                            print(f"⚠️  Fichier trop gros : {file_size_mb:.2f} MB (max 10MB)")
                            say(f"⚠️  {attachment_info['filename']} est trop gros ({file_size_mb:.1f}MB), max 10MB")
                            continue
                        
                        attachments_to_upload.append({
                            "filename": attachment_info["filename"],
                            "data": response.content
                        })
                        print(f"✅ Fichier téléchargé : {attachment_info['filename']}")
                    else:
                        print(f"⚠️  Échec téléchargement : {attachment_info['filename']}")
                        
                except Exception as e:
                    print(f"❌ Erreur téléchargement fichier : {e}")
        
        # Créer le ticket avec le bon client
        result = current_jira_client.create_issue(
            summary=jira_data["title"],
            description=jira_data["description"],
            priority_id=jira_data.get("priority_id"),
            component_ids=jira_data.get("component_ids"),
            labels=jira_data.get("labels"),
            medical_status_id=jira_data.get("medical_status_id"),
            impact_team_ids=jira_data.get("impact_team_ids"),
            attachments=attachments_to_upload if attachments_to_upload else None
        )
        
        # Nettoyer le contexte
        conv_manager.update_context(user_id, jira_ready=None, attachments=[], platform=None, current_ticket=None)
        
        # Confirmation avec lien
        platform_emoji = "🍎" if platform == "ios" else "🤖"
        ticket_key = result['key']
        say(f"✅ Ticket créé avec succès !\n{platform_emoji} *{ticket_key}*\n{result['url']}")
        
    except Exception as e:
        say(f"❌ Erreur lors de la création : {str(e)}")
        print(f"Error creating Jira ticket: {e}")
        import traceback
        traceback.print_exc()

@app.action("cancel_jira_creation")
def handle_cancel_creation(ack, body, say):
    """
    Annule la création du ticket.
    """
    ack()
    
    user_id = body["user"]["id"]
    conv_manager.update_context(user_id, jira_ready=None)
    
    say("❌ Création annulée.")

def parse_ticket_for_jira(ticket_text: str) -> Dict:
    """
    Parse le ticket généré pour extraire titre et description.
    """
    try:
        # Chercher le titre
        title_match = re.search(r'\*?Title:?\*?\s*(.+)', ticket_text, re.IGNORECASE)
        if not title_match:
            title_match = re.search(r'^(.+)$', ticket_text.split('\n')[0])
        
        if not title_match:
            return None
        
        title = title_match.group(1).strip()
        
        # Extraire la description (tout le reste)
        description = ticket_text
        
        return {
            "title": title,
            "description": description
        }
    except Exception as e:
        print(f"Error parsing ticket: {e}")
        return None

def get_priority_name(priority_id: str, metadata: Dict) -> str:
    """Récupère le nom de la priorité depuis son ID"""
    if not priority_id or "priority" not in metadata.get("available_fields", {}):
        return "Non définie"
    
    for opt in metadata["available_fields"]["priority"]["options"]:
        if opt["id"] == priority_id:
            return opt["name"]
    
    return "Non définie"

def get_medical_status_name(status_id: str, metadata: Dict) -> str:
    """Récupère le nom du medical status depuis son ID"""
    if not status_id or "medical_status" not in metadata.get("available_fields", {}):
        return "Non défini"
    
    for opt in metadata["available_fields"]["medical_status"]["options"]:
        if opt["id"] == status_id:
            return opt["value"]
    
    return "Non défini"

def get_impact_team_names(team_ids: list, metadata: Dict) -> list:
    """Récupère les noms des impact teams depuis leurs IDs"""
    if not team_ids or "impact_team" not in metadata.get("available_fields", {}):
        return []
    
    names = []
    for team_id in team_ids:
        for opt in metadata["available_fields"]["impact_team"]["options"]:
            if opt["id"] == team_id:
                names.append(opt["value"])
                break
    
    return names

def get_component_names(component_ids: list, metadata: Dict) -> list:
    """Récupère les noms des composants depuis leurs IDs"""
    if not component_ids or "components" not in metadata.get("available_fields", {}):
        return []
    
    names = []
    for comp_id in component_ids:
        for opt in metadata["available_fields"]["components"]["options"]:
            if opt["id"] == comp_id:
                names.append(opt["name"])
                break
    
    return names

def handle_reset_command(user_id: str, say):
    """
    Réinitialise la conversation.
    """
    conv_manager.clear_conversation(user_id)
    say("🔄 Conversation réinitialisée ! On repart de zéro.")

@app.event("file_shared")
def handle_file_shared_event(event, say, client, ack):
    """
    Gère les fichiers uploadés via l'event file_shared.
    """
    ack()
    
    print("📎 FILE_SHARED event reçu")
    
    try:
        file_id = event.get("file_id")
        user_id = event.get("user_id")
        
        # Récupérer les infos du fichier
        file_info = client.files_info(file=file_id)
        file_data = file_info["file"]
        
        print(f"📄 Fichier: {file_data['name']} - Type: {file_data.get('mimetype')}")
        
        # Vérifier si c'est un PDF
        if file_data.get("mimetype") == "application/pdf" or file_data["name"].lower().endswith(".pdf"):
            say("📄 PDF détecté ! Je l'analyse pour générer un plan de test...")
            
            # Télécharger le fichier
            file_url = file_data["url_private"]
            headers = {"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
            response = requests.get(file_url, headers=headers)
            
            print(f"📥 Téléchargement: {response.status_code}")
            
            # Sauvegarder temporairement
            temp_path = f"/tmp/{file_data['name']}"
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            print(f"💾 Sauvegardé: {temp_path}")
            
            # Extraire le contenu du PDF
            from prd_parser import extract_pdf_content
            prd_content = extract_pdf_content(temp_path)
            
            print(f"📖 Contenu extrait: {len(prd_content)} caractères")
            
            # Générer le plan de test
            from testplan_generator import generate_testplan_from_prd
            testplan = generate_testplan_from_prd(
                prd_content,
                prd_source=f"PDF: {file_data['name']}"
            )
            
            # Envoyer le plan de test
            say(testplan)
            
            # Nettoyer
            try:
                os.remove(temp_path)
                print("✅ Plan de test envoyé")
            except FileNotFoundError:
                print("✅ Plan de test envoyé (fichier déjà nettoyé)")
            
        else:
            # C'est un fichier image/vidéo pour un ticket
            file_type = file_data.get("mimetype", "")
            
            if file_type.startswith("image/") or file_type.startswith("video/"):
                # Stocker dans le contexte pour utilisation future
                context = conv_manager.get_context(user_id)
                
                if "attachments" not in context:
                    context["attachments"] = []
                
                # Ajouter l'info du fichier
                context["attachments"].append({
                    "file_id": file_id,
                    "filename": file_data["name"],
                    "url": file_data["url_private"],
                    "type": file_type,
                    "size": file_data.get("size", 0)
                })
                
                conv_manager.update_context(user_id, attachments=context["attachments"])
                
                # Confirmer à l'user
                file_emoji = "🎥" if file_type.startswith("video/") else "📸"
                say(f"{file_emoji} Fichier récupéré : *{file_data['name']}*\nJe l'ajouterai automatiquement au ticket Jira quand tu le créeras !")
            else:
                say(f"✅ Fichier récupéré : {file_data['name']}")
            
    except Exception as e:
        say(f"❌ Erreur lors de l'analyse du fichier : {str(e)}")
        print(f"❌ Erreur file_shared: {e}")
        import traceback
        traceback.print_exc()

@app.event("app_mention")
def handle_mention(event, say):
    """Gère les mentions"""
    say("Salut ! 👋 \nAlors, qu'est-ce qui se passe ? Un bug à signaler ou tu veux juste discuter ?")

if __name__ == "__main__":
    print("⚡️ QA Agent V2 démarré")
    print("🎭 Personnalité Claude-like activée")
    print("🎯 Questions intelligentes activées")
    print("📝 Mémoire conversationnelle activée")
    print("📱 Détection iOS/Android activée")
    if jira_enabled:
        print("🎫 Intégration Jira activée (avec confirmation)")
    print("")
    print("Commandes :")
    print("  - 'reset' : Réinitialiser")
    print("  - 'copy' : Copier partie anglaise")
    
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()