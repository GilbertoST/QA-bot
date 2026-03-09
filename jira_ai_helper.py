"""
AI Helper pour remplir intelligemment les champs Jira
Version avec custom fields Withings
"""
import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

JIRA_FIELD_FILLER_PROMPT = """Tu es un expert en création de tickets Jira qui remplit intelligemment les champs selon le contexte du bug.

**TON RÔLE:**
Analyser un ticket de bug et choisir les bonnes valeurs pour les champs Jira.

**CHAMPS DISPONIBLES:**
{metadata}

**TICKET À ANALYSER:**
{ticket_content}

**TES RÈGLES DE DÉCISION:**

1. **Priority** (choisis parmi les options disponibles) :
   - Critical/Highest : Crash systématique, blocage complet, perte de données
   - High : Crash aléatoire, feature majeure cassée
   - Medium : Bug fonctionnel mais workaround possible
   - Low : Cosmétique, typo, amélioration mineure

2. **Medical Status** (OBLIGATOIRE - choisis parmi les options) :
   - "High Medical Impact" : Bug critique affectant des mesures médicales (ECG, SpO2, température, pression artérielle)
   - "Low Medical Impact" : Bug mineur sur features médicales mais pas critique
   - "Unknown Medical Impact" : Incertain si ça affecte le médical
   - "Not Medical" : Bug purement cosmétique, UI, non lié aux mesures de santé

3. **Impact Team** (OBLIGATOIRE - choisis 1 ou plusieurs équipes concernées) :
   - "Core Topics" : Si lié aux mesures, données, synchronisation
   - "Core UX" : Si lié à l'interface utilisateur, navigation
   - "le with HS4" : Si lié aux appareils spécifiques
   - Autres selon le contexte du bug

4. **Labels** (texte libre, max 5 labels) :
   - "sqa" sera ajouté automatiquement (ne l'inclus pas)
   - Platform : "iOS", "Android"
   - Device : "iPhone", "Pixel", etc.
   - Withings device : "ScanWatch2", "BodyPlus", etc.
   - Type : "crash", "ui-bug", "sync-issue"

**FORMAT DE RÉPONSE (JSON uniquement) :**
```json
{{
  "priority_id": "id de la priorité",
  "medical_status_id": "id du medical status",
  "impact_team_ids": ["id1", "id2"],
  "labels": ["iOS", "crash", "ScanWatch2"],
  "reasoning": "Explication de tes choix"
}}
```

**IMPORTANT:**
- Utilise UNIQUEMENT les IDs présents dans la metadata
- Medical Status est OBLIGATOIRE
- Impact Team est OBLIGATOIRE (au moins 1)
- Reste factuel, pas de spéculation"""

def fill_jira_fields_with_ai(ticket_content: str, jira_metadata: Dict, max_retries: int = 3) -> Dict:
    """
    Utilise l'AI pour remplir intelligemment les champs Jira.
    Avec retry automatique.
    
    Args:
        ticket_content: Le contenu complet du ticket (title + description)
        jira_metadata: Les métadonnées Jira (options disponibles)
        max_retries: Nombre de tentatives max
        
    Returns:
        Dict avec priority_id, medical_status_id, impact_team_ids, labels
    """
    for attempt in range(max_retries):
        try:
            # Formater la metadata pour le prompt
            metadata_str = format_metadata_for_prompt(jira_metadata)
            
            # Appeler Claude pour choisir les champs
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": JIRA_FIELD_FILLER_PROMPT.format(
                        metadata=metadata_str,
                        ticket_content=ticket_content
                    )
                }]
            )
            
            response_text = message.content[0].text
            
            # Parser la réponse JSON
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
            else:
                json_str = response_text.strip()
            
            result = json.loads(json_str)
            
            return {
                "priority_id": result.get("priority_id"),
                "medical_status_id": result.get("medical_status_id"),
                "impact_team_ids": result.get("impact_team_ids", []),
                "component_ids": result.get("component_ids", []),
                "labels": result.get("labels", []),
                "reasoning": result.get("reasoning", "")
            }
            
        except Exception as e:
            error_str = str(e)
            
            # Retry si overload
            if "overloaded" in error_str.lower() and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"API overloaded, retry in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            print(f"Error filling Jira fields with AI: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback : valeurs par défaut sécurisées
            default_medical = None
            default_impact = []
            
            if "medical_status" in jira_metadata.get("available_fields", {}):
                for opt in jira_metadata["available_fields"]["medical_status"]["options"]:
                    if "unknown" in opt["value"].lower():
                        default_medical = opt["id"]
                        break
            
            if "impact_team" in jira_metadata.get("available_fields", {}):
                for opt in jira_metadata["available_fields"]["impact_team"]["options"]:
                    if "core topics" in opt["value"].lower():
                        default_impact = [opt["id"]]
                        break
            
            return {
                "priority_id": None,
                "medical_status_id": default_medical,
                "impact_team_ids": default_impact,
                "component_ids": [],
                "labels": [],
                "reasoning": "Failed to analyze, using defaults"
            }
    """
    Utilise l'AI pour remplir intelligemment les champs Jira.
    
    Args:
        ticket_content: Le contenu complet du ticket (title + description)
        jira_metadata: Les métadonnées Jira (options disponibles)
        
    Returns:
        Dict avec priority_id, medical_status_id, impact_team_ids, labels
    """
    try:
        # Formater la metadata pour le prompt
        metadata_str = format_metadata_for_prompt(jira_metadata)
        
        # Appeler Claude pour choisir les champs
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": JIRA_FIELD_FILLER_PROMPT.format(
                    metadata=metadata_str,
                    ticket_content=ticket_content
                )
            }]
        )
        
        response_text = message.content[0].text
        
        # Parser la réponse JSON
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text.strip()
        
        result = json.loads(json_str)
        
        return {
            "priority_id": result.get("priority_id"),
            "medical_status_id": result.get("medical_status_id"),
            "impact_team_ids": result.get("impact_team_ids", []),
            "component_ids": result.get("component_ids", []),
            "labels": result.get("labels", []),
            "reasoning": result.get("reasoning", "")
        }
        
    except Exception as e:
        print(f"Error filling Jira fields with AI: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback : valeurs par défaut sécurisées
        default_medical = None
        default_impact = []
        
        if "medical_status" in jira_metadata.get("available_fields", {}):
            # Prendre "Unknown Medical Impact" par défaut
            for opt in jira_metadata["available_fields"]["medical_status"]["options"]:
                if "unknown" in opt["value"].lower():
                    default_medical = opt["id"]
                    break
        
        if "impact_team" in jira_metadata.get("available_fields", {}):
            # Prendre "Core Topics" par défaut
            for opt in jira_metadata["available_fields"]["impact_team"]["options"]:
                if "core topics" in opt["value"].lower():
                    default_impact = [opt["id"]]
                    break
        
        return {
            "priority_id": None,
            "medical_status_id": default_medical,
            "impact_team_ids": default_impact,
            "component_ids": [],
            "labels": [],
            "reasoning": "Failed to analyze, using defaults"
        }

def format_metadata_for_prompt(metadata: Dict) -> str:
    """Formate les métadonnées Jira pour le prompt"""
    output = []
    
    # Priority
    if "priority" in metadata.get("available_fields", {}):
        output.append("**Priority options:**")
        for opt in metadata["available_fields"]["priority"]["options"]:
            output.append(f"  - {opt['name']} (id: {opt['id']})")
    
    # Medical Status
    if "medical_status" in metadata.get("available_fields", {}):
        output.append("\n**Medical Status options (OBLIGATOIRE):**")
        for opt in metadata["available_fields"]["medical_status"]["options"]:
            output.append(f"  - {opt['value']} (id: {opt['id']})")
    
    # Impact Team
    if "impact_team" in metadata.get("available_fields", {}):
        output.append("\n**Impact Team options (OBLIGATOIRE, plusieurs possibles):**")
        for opt in metadata["available_fields"]["impact_team"]["options"]:
            output.append(f"  - {opt['value']} (id: {opt['id']})")
    
    # Components
    if "components" in metadata.get("available_fields", {}):
        output.append("\n**Component options:**")
        for opt in metadata["available_fields"]["components"]["options"]:
            output.append(f"  - {opt['name']} (id: {opt['id']})")
    
    # Labels
    if "labels" in metadata.get("available_fields", {}):
        output.append("\n**Labels:** Free text (max 5, 'sqa' sera ajouté automatiquement)")
    
    return "\n".join(output)