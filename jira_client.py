"""
Client Jira avec intelligence AI pour remplir les champs
Version avec custom fields Withings + Format ADF avec couleurs
"""
import os
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

class JiraClient:
    """Client intelligent pour interagir avec Jira"""
    
    def __init__(self):
        self.base_url = os.getenv("JIRA_URL")  # Ex: https://yourcompany.atlassian.net
        self.email = os.getenv("JIRA_EMAIL")
        self.api_token = os.getenv("JIRA_API_TOKEN")
        self.project_key = os.getenv("JIRA_PROJECT_KEY")  # Ex: "HMIOS" ou "HMANDROID"
        
        if not all([self.base_url, self.email, self.api_token, self.project_key]):
            raise ValueError("Missing Jira credentials in .env")
        
        self.auth = (self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def get_create_metadata(self) -> Dict:
        """
        Récupère les métadonnées pour créer un ticket.
        Retourne les champs disponibles, leurs types, et les options des dropdowns.
        """
        url = f"{self.base_url}/rest/api/3/issue/createmeta"
        params = {
            "projectKeys": self.project_key,
            "expand": "projects.issuetypes.fields"
        }
        
        response = requests.get(
            url,
            auth=self.auth,
            headers=self.headers,
            params=params
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get metadata: {response.text}")
        
        return response.json()
    
    def parse_metadata_for_ai(self) -> Dict:
        """
        Parse les métadonnées Jira dans un format facile pour l'AI.
        Retourne les options disponibles pour chaque champ (y compris custom fields).
        """
        try:
            metadata = self.get_create_metadata()
            
            # Vérifier que projects existe et n'est pas vide
            if "projects" not in metadata or len(metadata["projects"]) == 0:
                raise Exception(f"No projects found in metadata. Response: {metadata}")
            
            # Extraire le projet
            project = metadata["projects"][0]
            
            # Vérifier que issuetypes existe
            if "issuetypes" not in project or len(project["issuetypes"]) == 0:
                raise Exception(f"No issue types found in project. Project: {project}")
            
            # Extraire le type d'issue "Bug"
            bug_type = None
            
            for issuetype in project["issuetypes"]:
                if issuetype["name"].lower() == "bug":
                    bug_type = issuetype
                    break
            
            if not bug_type:
                # Prendre le premier type disponible
                print(f"Warning: 'Bug' issue type not found. Using first available: {project['issuetypes'][0]['name']}")
                bug_type = project["issuetypes"][0]
            
            fields = bug_type["fields"]
            
            # Parser les champs importants
            parsed = {
                "issue_type_id": bug_type["id"],
                "available_fields": {}
            }
            
            # Priority
            if "priority" in fields:
                parsed["available_fields"]["priority"] = {
                    "required": fields["priority"].get("required", False),
                    "options": [
                        {"id": opt["id"], "name": opt["name"]}
                        for opt in fields["priority"].get("allowedValues", [])
                    ]
                }
            
            # Components
            if "components" in fields:
                parsed["available_fields"]["components"] = {
                    "required": fields["components"].get("required", False),
                    "options": [
                        {"id": opt["id"], "name": opt["name"]}
                        for opt in fields["components"].get("allowedValues", [])
                    ]
                }
            
            # Labels (toujours disponible)
            if "labels" in fields:
                parsed["available_fields"]["labels"] = {
                    "required": fields["labels"].get("required", False),
                    "free_text": True  # Labels sont en texte libre
                }
            
            # Assignee
            if "assignee" in fields:
                parsed["available_fields"]["assignee"] = {
                    "required": fields["assignee"].get("required", False),
                    "can_be_null": True
                }
            
            # NOUVEAU : Parcourir tous les champs pour trouver les custom fields
            for field_key, field_data in fields.items():
                field_name = field_data.get("name", "")
                
                # Medical Status (custom field)
                if "medical status" in field_name.lower():
                    parsed["available_fields"]["medical_status"] = {
                        "key": field_key,
                        "name": field_name,
                        "required": field_data.get("required", False),
                        "options": [
                            {"id": opt["id"], "value": opt["value"]}
                            for opt in field_data.get("allowedValues", [])
                        ]
                    }
                
                # Impact Team (custom field)
                elif "impact team" in field_name.lower():
                    parsed["available_fields"]["impact_team"] = {
                        "key": field_key,
                        "name": field_name,
                        "required": field_data.get("required", False),
                        "options": [
                            {"id": opt["id"], "value": opt["value"]}
                            for opt in field_data.get("allowedValues", [])
                        ]
                    }
            
            return parsed
            
        except Exception as e:
            print(f"Error parsing Jira metadata: {e}")
            import traceback
            traceback.print_exc()
            # Retourner une structure minimale pour que ça ne crash pas
            return {
                "issue_type_id": None,
                "available_fields": {}
            }
    
    def create_issue(
        self,
        summary: str,
        description: str,
        priority_id: Optional[str] = None,
        component_ids: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        assignee_id: Optional[str] = None,
        medical_status_id: Optional[str] = None,
        impact_team_ids: Optional[List[str]] = None,
        attachments: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Crée un ticket Jira avec les champs spécifiés.
        
        Args:
            summary: Titre du ticket
            description: Description (format texte simple)
            priority_id: ID de la priorité
            component_ids: Liste des IDs de composants
            labels: Liste de labels (texte libre)
            assignee_id: ID de l'assignee (ou None pour unassigned)
            medical_status_id: ID du Medical Status (custom field)
            impact_team_ids: Liste des IDs des Impact Teams (custom field)
            attachments: Liste de fichiers à uploader
            
        Returns:
            Dict avec les infos du ticket créé (key, id, url)
        """
        metadata = self.parse_metadata_for_ai()
        
        # Construire le payload
        fields = {
            "project": {"key": self.project_key},
            "issuetype": {"id": metadata["issue_type_id"]},
            "summary": summary,
            "description": self._format_description_for_jira(description)
        }
        
        # Ajouter les champs optionnels
        if priority_id:
            fields["priority"] = {"id": priority_id}
        
        if component_ids:
            fields["components"] = [{"id": cid} for cid in component_ids]
        
        # Labels : TOUJOURS ajouter "sqa"
        if not labels:
            labels = []
        if "sqa" not in labels:
            labels.append("sqa")
        fields["labels"] = labels
        
        if assignee_id:
            fields["assignee"] = {"id": assignee_id}
        
        # NOUVEAU : Custom fields
        # Medical Status
        if medical_status_id and "medical_status" in metadata["available_fields"]:
            field_key = metadata["available_fields"]["medical_status"]["key"]
            fields[field_key] = {"id": medical_status_id}
        
        # Impact Team
        if impact_team_ids and "impact_team" in metadata["available_fields"]:
            field_key = metadata["available_fields"]["impact_team"]["key"]
            fields[field_key] = [{"id": team_id} for team_id in impact_team_ids]
        
        # Créer le ticket
        url = f"{self.base_url}/rest/api/3/issue"
        payload = {"fields": fields}
        
        print(f"DEBUG - Payload Jira: {payload}")  # Pour debug
        
        response = requests.post(
            url,
            auth=self.auth,
            headers=self.headers,
            json=payload
        )
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create issue: {response.text}")
        
        result = response.json()
        issue_key = result["key"]
        issue_id = result["id"]
        
        # Upload attachments si présents
        if attachments:
            for attachment in attachments:
                self.add_attachment(issue_id, attachment)
        
        return {
            "key": issue_key,
            "id": issue_id,
            "url": f"{self.base_url}/browse/{issue_key}"
        }
    
    def _format_description_for_jira(self, markdown_text: str) -> Dict:
        """
        Convertit le ticket en format Jira ADF avec panels colorés.
        """
        # Parser le ticket markdown
        lines = markdown_text.split("\n")
        
        # Extraire les sections
        current_behavior = []
        expected_behavior = []
        how_to_reproduce = []
        reproduced_on = []
        
        current_section = None
        
        for line in lines:
            line_stripped = line.strip()
            
            if "*Current behavior*" in line or "Current behavior" in line:
                current_section = "current"
            elif "*Expected behavior*" in line or "Expected behavior" in line:
                current_section = "expected"
            elif "*How to reproduce*" in line or "How to reproduce" in line:
                current_section = "reproduce"
            elif "*Reproduced on*" in line or "Reproduced on" in line:
                current_section = "reproduced"
            elif line_stripped and current_section:
                # Nettoyer les bullets markdown
                clean_line = line_stripped.replace("- ", "").replace("* ", "")
                
                if current_section == "current":
                    current_behavior.append(clean_line)
                elif current_section == "expected":
                    expected_behavior.append(clean_line)
                elif current_section == "reproduce":
                    how_to_reproduce.append(clean_line)
                elif current_section == "reproduced":
                    reproduced_on.append(clean_line)
        
        # Construire l'ADF avec panels colorés
        content = []
        
        # Current behavior - Panel ROUGE (error)
        if current_behavior:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "error"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Current behavior", "marks": [{"type": "strong"}]}
                        ]
                    }
                ]
            })
            
            # UNE SEULE bulletList avec tous les items
            bullet_items = [
                {
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item}]
                    }]
                }
                for item in current_behavior
            ]
            
            content.append({
                "type": "bulletList",
                "content": bullet_items
            })
        
        # Expected behavior - Panel VERT (success)
        if expected_behavior:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "success"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Expected behavior", "marks": [{"type": "strong"}]}
                        ]
                    }
                ]
            })
            
            bullet_items = [
                {
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item}]
                    }]
                }
                for item in expected_behavior
            ]
            
            content.append({
                "type": "bulletList",
                "content": bullet_items
            })
        
        # How to reproduce - Panel BLEU (info)
        if how_to_reproduce:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "info"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "How to reproduce", "marks": [{"type": "strong"}]}
                        ]
                    }
                ]
            })
            
            # UNE SEULE orderedList avec tous les steps
            ordered_items = [
                {
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item}]
                    }]
                }
                for item in how_to_reproduce
            ]
            
            content.append({
                "type": "orderedList",
                "content": ordered_items
            })
        
        # Reproduced on - Panel VIOLET (note)
        if reproduced_on:
            content.append({
                "type": "panel",
                "attrs": {"panelType": "note"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Additional information", "marks": [{"type": "strong"}]}
                        ]
                    }
                ]
            })
            
            bullet_items = [
                {
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": item}]
                    }]
                }
                for item in reproduced_on
            ]
            
            content.append({
                "type": "bulletList",
                "content": bullet_items
            })
        
        # Si on n'a rien parsé, fallback sur le texte brut
        if not content:
            content = [{
                "type": "paragraph",
                "content": [{"type": "text", "text": markdown_text}]
            }]
        
        return {
            "type": "doc",
            "version": 1,
            "content": content
        }
    
    def add_attachment(self, issue_id: str, attachment: Dict):
        """
        Ajoute un fichier en pièce jointe à un ticket.
        
        Args:
            issue_id: ID du ticket Jira
            attachment: Dict avec 'filename' et 'data' (bytes)
        """
        url = f"{self.base_url}/rest/api/3/issue/{issue_id}/attachments"
        
        # Headers spéciaux pour upload
        headers = {
            "X-Atlassian-Token": "no-check"
        }
        
        files = {
            'file': (attachment['filename'], attachment['data'])
        }
        
        # Augmenter le timeout pour les vidéos (30 secondes)
        try:
            response = requests.post(
                url,
                auth=self.auth,
                headers=headers,
                files=files,
                timeout=30  # 30 secondes pour les grosses vidéos
            )
            
            if response.status_code in [200, 201]:
                print(f"✅ Attachment uploadé : {attachment['filename']}")
            else:
                print(f"❌ Failed to upload attachment: {response.status_code} - {response.text}")
        
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout lors de l'upload de {attachment['filename']} (fichier trop gros ou connexion lente)")
        except Exception as e:
            print(f"❌ Erreur upload: {e}")