import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from core.logger import logger
from core.database import db

# Added Google People API readonly scope
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts.readonly'
]

class ContactsService:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None
        self.service = None
        self.init_cache_table()

    def init_cache_table(self):
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        name TEXT,
                        phone TEXT,
                        interaction_count INTEGER DEFAULT 0,
                        last_contacted_timestamp TEXT,
                        display_override TEXT
                    )
                """)
                # Migrations in case table already existed without these columns
                cursor.execute("PRAGMA table_info(contacts)")
                columns = [row[1] for row in cursor.fetchall()]
                if "interaction_count" not in columns:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN interaction_count INTEGER DEFAULT 0")
                if "last_contacted_timestamp" not in columns:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN last_contacted_timestamp TEXT")
                if "display_override" not in columns:
                    cursor.execute("ALTER TABLE contacts ADD COLUMN display_override TEXT")
                conn.commit()
                logger.info("SQLite contacts cache table initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize contacts database table: {e}")

    def authenticate(self) -> Credentials:
        """
        Authenticates/loads stored credentials or runs the OAuth flow if expired/missing.
        """
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                logger.error(f"Error reading token.json: {e}")

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    logger.info("Credentials refreshed successfully.")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Google OAuth credentials file not found at {self.credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            with open(self.token_path, 'w') as token:
                token.write(self.creds.to_json())
                logger.info(f"Token saved successfully to {self.token_path}")

        self.service = build('people', 'v1', credentials=self.creds)
        return self.creds

    def get_service(self):
        if not self.service:
            self.authenticate()
        return self.service

    def refresh_contacts(self) -> int:
        """
        Fetches all contacts from Google People API and updates the local SQLite cache.
        """
        service = self.get_service()
        logger.info("Refreshing contacts from Google People API...")
        
        all_contacts = []
        next_page_token = None
        
        while True:
            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,phoneNumbers',
                pageToken=next_page_token
            ).execute()
            
            connections = results.get('connections', [])
            for person in connections:
                names = person.get('names', [])
                phone_numbers = person.get('phoneNumbers', [])
                
                if not names or not phone_numbers:
                    continue
                
                name = names[0].get('displayName')
                
                # Extract primary or first phone number
                primary_phone = None
                primaries = [p.get('value') for p in phone_numbers if p.get('metadata', {}).get('primary')]
                if primaries:
                    primary_phone = primaries[0]
                else:
                    primary_phone = phone_numbers[0].get('value')
                
                if name and primary_phone:
                    # Basic cleaning of phone number
                    cleaned_phone = re.sub(r"[^\d+]", "", primary_phone)
                    all_contacts.append((name, cleaned_phone))
            
            next_page_token = results.get('nextPageToken')
            if not next_page_token:
                break
        
        # Update local SQLite cache while preserving interaction counts, last contacted timestamps, and display overrides
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Read existing history by phone number to be stable across renames
            cursor.execute("PRAGMA table_info(contacts)")
            columns = [row[1] for row in cursor.fetchall()]
            history = {}
            query_cols = []
            if "interaction_count" in columns:
                query_cols.append("interaction_count")
            if "last_contacted_timestamp" in columns:
                query_cols.append("last_contacted_timestamp")
            if "display_override" in columns:
                query_cols.append("display_override")
            
            if "phone" in columns and query_cols:
                cols_str = ", ".join(query_cols)
                cursor.execute(f"SELECT phone, {cols_str} FROM contacts")
                rows = cursor.fetchall()
                for r in rows:
                    p = r[0]
                    if not p:
                        continue
                    vals = r[1:]
                    cnt = vals[query_cols.index("interaction_count")] if "interaction_count" in query_cols else 0
                    ts = vals[query_cols.index("last_contacted_timestamp")] if "last_contacted_timestamp" in query_cols else None
                    override = vals[query_cols.index("display_override")] if "display_override" in query_cols else None
                    history[p] = (cnt, ts, override)
            
            cursor.execute("DELETE FROM contacts")
            
            extended_contacts = []
            for name, phone in all_contacts:
                count, ts, override = history.get(phone, (0, None, None))
                extended_contacts.append((name, phone, count, ts, override))
                
            cursor.executemany(
                "INSERT INTO contacts (name, phone, interaction_count, last_contacted_timestamp, display_override) VALUES (?, ?, ?, ?, ?)",
                extended_contacts
            )
            conn.commit()
            
        logger.info(f"Successfully cached {len(all_contacts)} contacts.")
        return len(all_contacts)

    def resolve_contact(self, name_query: str) -> dict:
        """
        Resolves a search reference to a single cached contact.
        - Exact matches (case-insensitive) are preferred.
        - Token-overlap scoring handles multi-word/partial matches.
        - Substring matches are scored and returned as fallback.
        - Minimum match confidence threshold is 0.75.
        - Returns a dictionary detailing status: "resolved", "no_match", or "ambiguous".
        """
        target = name_query.strip().lower()
        if not target:
            return {"status": "no_match"}

        # Fetch all cached contacts including overrides
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, phone, display_override FROM contacts")
            contacts = [
                {"name": row[0], "phone": row[1], "display_override": row[2]} 
                for row in cursor.fetchall()
            ]

        # Helper to clean strings for better token matching (remove emojis, punctuation)
        def clean_str(s: str) -> str:
            return re.sub(r"[^\w\s]", "", s).strip().lower()

        cleaned_target = clean_str(target)
        target_tokens = set(cleaned_target.split())

        # Collect all matches with their scores
        matches_with_scores = []

        for c in contacts:
            c_name_lower = c["name"].lower()
            cleaned_c_name = clean_str(c_name_lower)
            c_tokens = set(cleaned_c_name.split())
            
            c_override_lower = c["display_override"].lower() if c["display_override"] else None
            cleaned_c_override = clean_str(c_override_lower) if c_override_lower else None
            c_override_tokens = set(cleaned_c_override.split()) if cleaned_c_override else set()
            
            score = 0.0
            # Tier 1: Exact Match (either name or override)
            if (c_name_lower == target or cleaned_c_name == cleaned_target or
                (c_override_lower and (c_override_lower == target or cleaned_c_override == cleaned_target))):
                score = 1.0
            # Tier 2: Token Overlap
            elif target_tokens and (c_tokens or c_override_tokens):
                score_name = len(target_tokens & c_tokens) / len(target_tokens) if c_tokens else 0.0
                score_override = len(target_tokens & c_override_tokens) / len(target_tokens) if c_override_tokens else 0.0
                score = max(score_name, score_override)
            # Tier 3: Substring
            elif target in c_name_lower or (c_override_lower and target in c_override_lower):
                # Substring match score based on length ratio
                score_name = len(target) / len(c_name_lower) if target in c_name_lower else 0.0
                score_override = len(target) / len(c_override_lower) if (c_override_lower and target in c_override_lower) else 0.0
                score = max(score_name, score_override)
                
            if score >= 0.45:
                # Keep dict clean for callers who expect 'name' and 'phone'
                matches_with_scores.append((c, score))

        if not matches_with_scores:
            logger.info(f"resolve_contact: No contact matches above 0.45 threshold for '{name_query}'")
            return {"status": "no_match"}

        # Separate high confidence matches from near-misses
        high_conf_matches = [(c, score) for c, score in matches_with_scores if score >= 0.75]
        if high_conf_matches:
            best_score = max(score for _, score in high_conf_matches)
            best_candidates = [c for c, score in high_conf_matches if score == best_score]
            if len(best_candidates) == 1:
                logger.info(f"resolve_contact: resolved '{best_candidates[0]['name']}' (score={best_score:.2f})")
                return {"status": "resolved", "contact": best_candidates[0]}
            else:
                logger.info(f"resolve_contact: ambiguous match for '{name_query}' with {len(best_candidates)} candidates")
                return {"status": "ambiguous", "candidates": best_candidates}
        else:
            # Handle near-misses (0.45 <= score < 0.75)
            best_score = max(score for _, score in matches_with_scores)
            best_candidates = [c for c, score in matches_with_scores if score == best_score]
            if len(best_candidates) == 1:
                logger.info(f"resolve_contact: near-miss match '{best_candidates[0]['name']}' (score={best_score:.2f})")
                return {"status": "near_miss", "contact": best_candidates[0], "score": best_score}
            else:
                logger.info(f"resolve_contact: multiple near-miss candidates sharing score {best_score:.2f} for '{name_query}'")
                return {"status": "no_match"}

    def record_interaction(self, name: str):
        """
        Increments the interaction count and updates the last_contacted_timestamp
        for the contact with the exact name matching the DB entry.
        """
        if not name:
            return
        try:
            import datetime
            now = datetime.datetime.utcnow().isoformat()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE contacts SET interaction_count = interaction_count + 1, last_contacted_timestamp = ? WHERE name = ?",
                    (now, name)
                )
                conn.commit()
                # Verify that it updated something
                if cursor.rowcount > 0:
                    logger.info(f"Recorded interaction for contact '{name}' (updated {cursor.rowcount} rows)")
                else:
                    logger.info(f"record_interaction: Contact '{name}' not found in database to update count")
        except Exception as e:
            logger.error(f"Failed to record contact interaction for '{name}': {e}")

    def set_contact_override(self, name_query: str, override_name: str) -> str:
        """
        Sets a display override for a contact matched by name_query.
        """
        res = self.resolve_contact(name_query)
        if res["status"] == "no_match":
            return f"I couldn't find any contact matching '{name_query}' to rename."
        elif res["status"] == "ambiguous":
            candidates_str = ", ".join([c["name"] for c in res["candidates"]])
            return f"I found multiple contacts matching '{name_query}': {candidates_str}. Please be more specific."
        
        contact = res["contact"]
        canonical_name = contact["name"]
        phone = contact["phone"]
        
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE contacts SET display_override = ? WHERE phone = ?",
                    (override_name, phone)
                )
                conn.commit()
            logger.info(f"Set override for '{canonical_name}' (phone={phone}) to '{override_name}'")
            return f"I've set the alias for {canonical_name} to '{override_name}'."
        except Exception as e:
            logger.error(f"Failed to set contact override: {e}")
            return f"I was unable to update the contact's name."

contacts_service = ContactsService()
