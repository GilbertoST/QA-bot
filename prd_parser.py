"""
Parser pour extraire le contenu des PRDs (Notion et PDF)
"""
import os
import re
from typing import Dict, Optional
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def is_notion_url(text: str) -> bool:
    """Détecte si c'est un lien Notion"""
    notion_patterns = [
        r'https://www\.notion\.so/',
        r'https://[a-zA-Z0-9-]+\.notion\.site/',
        r'notion://'
    ]
    return any(re.search(pattern, text) for pattern in notion_patterns)

def extract_notion_url(text: str) -> Optional[str]:
    """Extrait l'URL Notion d'un message"""
    # Pattern pour détecter les URLs Notion
    patterns = [
        r'(https://www\.notion\.so/[^\s]+)',
        r'(https://[a-zA-Z0-9-]+\.notion\.site/[^\s]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    return None

def fetch_notion_content(notion_url: str) -> str:
    """
    Récupère le contenu d'une page Notion via MCP.
    
    Args:
        notion_url: URL de la page Notion
        
    Returns:
        Contenu de la page en markdown
    """
    try:
        # Utiliser Claude avec le MCP Notion pour fetch la page
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": f"Fetch this Notion page and return its full content: {notion_url}"
            }],
            tools=[{
                "type": "custom",
                "name": "notion-fetch"
            }]
        )
        
        # Extraire le contenu
        content = ""
        for block in message.content:
            if hasattr(block, 'text'):
                content += block.text + "\n"
        
        return content.strip()
        
    except Exception as e:
        raise Exception(f"Failed to fetch Notion page: {str(e)}")

def extract_pdf_content(pdf_path: str) -> str:
    """
    Extrait le texte d'un PDF.
    
    Args:
        pdf_path: Chemin vers le fichier PDF
        
    Returns:
        Contenu du PDF en texte brut
    """
    try:
        import PyPDF2
        
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        
        return text.strip()
        
    except Exception as e:
        raise Exception(f"Failed to extract PDF content: {str(e)}")