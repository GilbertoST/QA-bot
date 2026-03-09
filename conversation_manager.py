"""
Gestionnaire de conversations avec historique
"""
from typing import Dict, List
from datetime import datetime, timedelta

class ConversationManager:
    """
    Gère l'historique des conversations par utilisateur.
    Nettoie automatiquement les vieilles conversations.
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        # {user_id: {"messages": [...], "last_activity": datetime, "context": {...}}}
        self.conversations: Dict[str, dict] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
    
    def add_message(self, user_id: str, role: str, content: str):
        """Ajoute un message à l'historique"""
        if user_id not in self.conversations:
            self.conversations[user_id] = {
                "messages": [],
                "last_activity": datetime.now(),
                "context": {
                    "current_ticket": None,
                    "mode": None  # "ticket" ou "testplan"
                }
            }
        
        self.conversations[user_id]["messages"].append({
            "role": role,
            "content": content
        })
        self.conversations[user_id]["last_activity"] = datetime.now()
    
    def get_history(self, user_id: str, max_messages: int = 20) -> List[dict]:
        """
        Récupère l'historique de conversation.
        Limite à max_messages pour éviter de dépasser le context window.
        """
        if user_id not in self.conversations:
            return []
        
        # Vérifier si la session a expiré
        if self._is_session_expired(user_id):
            self.clear_conversation(user_id)
            return []
        
        messages = self.conversations[user_id]["messages"]
        
        # Garder les N derniers messages
        return messages[-max_messages:] if len(messages) > max_messages else messages
    
    def get_context(self, user_id: str) -> dict:
        """Récupère le contexte actuel (ticket en cours, mode, etc.)"""
        if user_id not in self.conversations:
            return {}
        return self.conversations[user_id]["context"]
    
    def update_context(self, user_id: str, **kwargs):
        """Met à jour le contexte"""
        if user_id not in self.conversations:
            self.conversations[user_id] = {
                "messages": [],
                "last_activity": datetime.now(),
                "context": {}
            }
        
        self.conversations[user_id]["context"].update(kwargs)
        self.conversations[user_id]["last_activity"] = datetime.now()
    
    def clear_conversation(self, user_id: str):
        """Efface l'historique d'un utilisateur"""
        if user_id in self.conversations:
            del self.conversations[user_id]
    
    def _is_session_expired(self, user_id: str) -> bool:
        """Vérifie si la session a expiré"""
        if user_id not in self.conversations:
            return True
        
        last_activity = self.conversations[user_id]["last_activity"]
        return datetime.now() - last_activity > self.session_timeout
    
    def cleanup_old_sessions(self):
        """Nettoie les sessions expirées (à appeler périodiquement)"""
        expired_users = [
            user_id for user_id in self.conversations
            if self._is_session_expired(user_id)
        ]
        
        for user_id in expired_users:
            self.clear_conversation(user_id)
        
        return len(expired_users)