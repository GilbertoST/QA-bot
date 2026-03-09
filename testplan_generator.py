"""
Générateur de plans de test depuis PRD
"""
import os
from anthropic import Anthropic
from dotenv import load_dotenv
from prompts import TESTPLAN_FROM_PRD_PROMPT

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def generate_testplan_from_prd(prd_content: str, prd_source: str = "PRD") -> str:
    """
    Génère un plan de test exhaustif à partir d'un PRD.
    
    Args:
        prd_content: Le contenu complet du PRD (texte ou markdown)
        prd_source: Source du PRD (pour context dans la réponse)
        
    Returns:
        Plan de test formaté
    """
    try:
        # Construire le prompt
        prompt = f"""Voici un PRD (Product Requirements Document) que je dois tester.

Source: {prd_source}

PRD Content:
{prd_content}

Génère un plan de test exhaustif pour cette feature selon le format spécifié."""

        # Appeler Claude avec le SYSTEM prompt PRD
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=TESTPLAN_FROM_PRD_PROMPT,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        return message.content[0].text
        
    except Exception as e:
        return f"❌ Erreur lors de la génération du plan de test: {str(e)}"