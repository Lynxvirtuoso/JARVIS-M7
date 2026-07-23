import os
import glob
import json
import re
from difflib import SequenceMatcher
from core.database import db
from core.logger import logger

class RagasService:
    def __init__(self):
        pass

    def import_ragas_from_files(self, ragas_dir: str = r"D:\Development\Ragas") -> dict:
        """
        Imports ragas from JSON files at the given directory.
        Handles duplicate resolution:
        - Drops 6 duplicates with identical scales: Āhiri, Sutradhāri, Mishramanolayam, Basant Bahār, Haridasapriya, Shankaraharigowla.
        - Renames 7 duplicates with differing scales using '(Parent melakarta janya)' suffixes.
        """
        json_files = glob.glob(os.path.join(ragas_dir, "*.json"))
        if not json_files:
            return {"status": "error", "message": "No JSON files found in directory"}

        all_items = []
        for f_path in sorted(json_files):
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "ragas" in data:
                        data = data["ragas"]
                    all_items.extend(data)
            except Exception as e:
                logger.error(f"Failed to read raga file {f_path}: {e}")
                return {"status": "error", "message": f"Read error on {os.path.basename(f_path)}: {e}"}

        # 1. Map ID -> Item for parent name resolution
        id_to_item = {item["id"]: item for item in all_items}
        
        def get_melakarta_name(parent_val):
            if parent_val is None:
                return ""
            try:
                p_id = int(parent_val)
                p_item = id_to_item.get(p_id)
                if p_item:
                    return p_item["name"]
            except ValueError:
                # Parent might already be a name string
                return str(parent_val)
            return ""

        # 2. Identify duplicates by name
        from collections import defaultdict
        by_name = defaultdict(list)
        for item in all_items:
            by_name[item["name"]].append(item)

        # duplicate definitions
        duplicates_to_drop = {
            "Āhiri", "Sutradhāri", "Mishramanolayam", "Basant Bahār", "Haridasapriya", "Shankaraharigowla"
        }
        duplicates_to_rename = {
            "Poornalalita", "Poornapanchamam", "Chittaranjani", "Gāra", "Sahāna", "Mahathi", "Suddha"
        }

        # Build list of final ragas to import
        processed_ragas = []
        dropped_count = 0
        renamed_count = 0

        for raga_name, entries in by_name.items():
            if len(entries) == 1:
                processed_ragas.append(entries[0])
            else:
                if raga_name in duplicates_to_drop:
                    # Keep only the first entry
                    processed_ragas.append(entries[0])
                    dropped_count += len(entries) - 1
                elif raga_name in duplicates_to_rename:
                    # Rename all entries to disambiguate
                    for entry in entries:
                        p_name = get_melakarta_name(entry.get("parent"))
                        if p_name:
                            entry["name"] = f"{raga_name} ({p_name} janya)"
                        else:
                            entry["name"] = f"{raga_name} (ID {entry['id']} janya)"
                        processed_ragas.append(entry)
                        renamed_count += 1
                else:
                    # Fallback for unexpected duplicate: keep first
                    processed_ragas.append(entries[0])
                    dropped_count += len(entries) - 1

        # 3. Write to database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Clear existing data first
            cursor.execute("DELETE FROM raga_notes")
            cursor.execute("DELETE FROM ragas")
            
            ragas_rows = []
            notes_rows = []
            
            for item in processed_ragas:
                r_id = item["id"]
                name = item["name"]
                cat = item["category"]
                tradition = "Carnatic"  # Default Carnatic
                
                # Determine parent_id if applicable
                parent_id = None
                parent_val = item.get("parent")
                if parent_val is not None:
                    try:
                        parent_id = int(parent_val)
                    except ValueError:
                        # Parent is represented by name string in some entries
                        # Find parent ID by name matching
                        p_str = str(parent_val)
                        cursor.execute("SELECT id FROM ragas WHERE name = ?", (p_str,))
                        p_row = cursor.fetchone()
                        if p_row:
                            parent_id = p_row[0]
                
                ragas_rows.append((r_id, name, cat, tradition, parent_id))
                
                # Notes mapping
                for note_idx, note in enumerate(item.get("arohanam", []), 1):
                    notes_rows.append((r_id, "arohana", note_idx, note))
                for note_idx, note in enumerate(item.get("avarohanam", []), 1):
                    notes_rows.append((r_id, "avarohana", note_idx, note))

            cursor.executemany(
                "INSERT INTO ragas (id, name, category, tradition, parent_id) VALUES (?, ?, ?, ?, ?)",
                ragas_rows
            )
            cursor.executemany(
                "INSERT INTO raga_notes (raga_id, scale_type, note_position, note) VALUES (?, ?, ?, ?)",
                notes_rows
            )
            conn.commit()

        logger.info(f"Raga database import complete: imported {len(ragas_rows)} ragas, {len(notes_rows)} notes. Dropped {dropped_count} duplicates, renamed {renamed_count} ragas.")
        return {
            "status": "success",
            "imported_ragas": len(ragas_rows),
            "imported_notes": len(notes_rows),
            "dropped_duplicates": dropped_count,
            "renamed_ragas": renamed_count
        }

    def resolve_raga(self, name_query: str) -> dict:
        """
        Resolves a raga name query.
        Supports fuzzy name search, exact match, and parent janya ambiguity handling.
        Returns:
            - {"status": "resolved", "raga": {...}}
            - {"status": "ambiguous", "candidates": [...]}
            - {"status": "no_match"}
        """
        target = name_query.strip().lower()
        if not target:
            return {"status": "no_match"}

        # Fetch all ragas
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, category, tradition, parent_id FROM ragas")
            all_ragas = [
                {"id": row[0], "name": row[1], "category": row[2], "tradition": row[3], "parent_id": row[4]}
                for row in cursor.fetchall()
            ]

        matches_with_scores = []
        for r in all_ragas:
            r_name = r["name"].lower()
            
            # Extract base name from renamed duplicate (e.g. "sahāna (harikāmbhōji janya)" -> "sahāna")
            base_name = re.sub(r"\s*\(.*?\)", "", r_name).strip()
            
            score = 0.0
            # Tier 1: Exact Match (either full name or base name)
            if r_name == target or base_name == target:
                score = 1.0
            else:
                # Tier 2: Fuzzy similarity
                ratio = SequenceMatcher(None, target, base_name).ratio()
                if ratio >= 0.85:
                    score = ratio
                    
            if score >= 0.85:
                matches_with_scores.append((r, score))

        if not matches_with_scores:
            return {"status": "no_match"}

        # Sort by score descending
        matches_with_scores.sort(key=lambda x: x[1], reverse=True)
        best_score = matches_with_scores[0][1]
        best_candidates = [item for item, score in matches_with_scores if score == best_score]

        if len(best_candidates) == 1:
            raga = best_candidates[0]
            # Attach notes
            raga["arohana"] = self.get_raga_notes(raga["id"], "arohana")
            raga["avarohana"] = self.get_raga_notes(raga["id"], "avarohana")
            return {"status": "resolved", "raga": raga}
        else:
            # Ambiguity detected (e.g. searching for "Sahāna" matches two parent-specific entries)
            for c in best_candidates:
                c["arohana"] = self.get_raga_notes(c["id"], "arohana")
                c["avarohana"] = self.get_raga_notes(c["id"], "avarohana")
            return {"status": "ambiguous", "candidates": best_candidates}

    def get_raga_notes(self, raga_id: int, scale_type: str) -> list:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT note FROM raga_notes WHERE raga_id = ? AND scale_type = ? ORDER BY note_position ASC",
                (raga_id, scale_type)
            )
            return [row[0] for row in cursor.fetchall()]

    def filter_ragas(self, category: str = None, parent_id: int = None) -> list:
        """Filters ragas by category or parent melakarta ID."""
        query = "SELECT id, name, category, tradition, parent_id FROM ragas WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if parent_id is not None:
            query += " AND parent_id = ?"
            params.append(parent_id)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [
                {"id": row[0], "name": row[1], "category": row[2], "tradition": row[3], "parent_id": row[4]}
                for row in cursor.fetchall()
            ]

ragas_service = RagasService()
