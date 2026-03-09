"""
Script de test pour vérifier la connexion Jira
"""
from jira_client import JiraClient

try:
    print("🔍 Test de connexion Jira...")
    
    client = JiraClient()
    print(f"✅ Client initialisé")
    print(f"   URL: {client.base_url}")
    print(f"   Project: {client.project_key}")
    print()
    
    print("🔍 Récupération des métadonnées...")
    metadata = client.get_create_metadata()
    print(f"✅ Métadonnées récupérées")
    print(f"   Nombre de projets: {len(metadata.get('projects', []))}")
    
    if metadata.get('projects'):
        project = metadata['projects'][0]
        print(f"   Projet: {project.get('name', 'Unknown')}")
        print(f"   Issue types: {[it['name'] for it in project.get('issuetypes', [])]}")
    print()
    
    print("🔍 Parse des métadonnées...")
    parsed = client.parse_metadata_for_ai()
    print(f"✅ Parsing réussi")
    print(f"   Issue type ID: {parsed.get('issue_type_id')}")
    print(f"   Champs disponibles: {list(parsed.get('available_fields', {}).keys())}")
    
    if "priority" in parsed.get("available_fields", {}):
        print(f"   Priorities: {[opt['name'] for opt in parsed['available_fields']['priority']['options']]}")
    
    if "components" in parsed.get("available_fields", {}):
        print(f"   Components: {[opt['name'] for opt in parsed['available_fields']['components']['options']]}")
    
    print()
    print("✅ Tous les tests sont passés !")
    
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()