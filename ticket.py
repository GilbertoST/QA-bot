"""
Générateur de tickets Jira avec support de l'historique conversationnel
Version avec retry
"""
import os
import time
from dotenv import load_dotenv
from anthropic import Anthropic
from prompts import TICKET_SYSTEM_PROMPT

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def generate_ticket_with_history(conversation_history: list, max_retries: int = 3) -> str:
    """
    Génère un ticket Jira en tenant compte de tout l'historique.
    Avec retry automatique en cas d'overload.
    
    Args:
        conversation_history: Liste de messages {"role": "user/assistant", "content": "..."}
        max_retries: Nombre de tentatives max
        
    Returns:
        Ticket formaté (anglais + français optionnel)
    """
    for attempt in range(max_retries):
        try:
            # Créer le message avec SYSTEM prompt + historique
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=TICKET_SYSTEM_PROMPT,
                messages=conversation_history
            )
            
            return message.content[0].text
            
        except Exception as e:
            error_str = str(e)
            
            # Si c'est une erreur overload et qu'il reste des tentatives
            if "overloaded" in error_str.lower() and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"API overloaded, retry in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            return f"❌ Erreur lors de la génération du ticket: {str(e)}"

# Fonction de compatibilité pour l'ancien code
def generate_ticket(user_message: str) -> str:
    """Version simple sans historique (fallback)"""
    return generate_ticket_with_history([{
        "role": "user",
        "content": user_message
    }])