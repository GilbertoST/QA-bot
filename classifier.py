"""
Classifier pour détecter l'intention de l'utilisateur
Version avec retry en cas d'overload
"""
import os
import time
from dotenv import load_dotenv
from anthropic import Anthropic
from prompts import CLASSIFIER_PROMPT

# Charger le .env AVANT de créer le client
load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def classify_intent(user_message: str, max_retries: int = 3) -> str:
    """
    Classifie l'intention de l'utilisateur avec retry automatique.
    
    Args:
        user_message: Le message de l'utilisateur
        max_retries: Nombre de tentatives max
        
    Returns:
        "ticket" ou "testplan"
    """
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{
                    "role": "user",
                    "content": CLASSIFIER_PROMPT.format(user_message=user_message)
                }]
            )
            
            intent = message.content[0].text.strip().lower()
            
            # Validation - on accepte uniquement "ticket" ou "testplan"
            if intent not in ["ticket", "testplan"]:
                # Par défaut on considère que c'est un ticket si pas clair
                return "ticket"
                
            return intent
            
        except Exception as e:
            error_str = str(e)
            
            # Si c'est une erreur overload (529) et qu'il reste des tentatives
            if "overloaded" in error_str.lower() and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s...
                print(f"API overloaded, retry in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            print(f"Erreur lors de la classification: {e}")
            # En cas d'erreur finale, on assume que c'est un ticket
            return "ticket"