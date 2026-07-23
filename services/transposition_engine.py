import re

NOTE_TO_SEMITONE = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6,
    "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11
}

SEMITONE_TO_NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SWARA_TO_SEMITONE_OFFSET = {
    "S": 0, "R1": 1, "R2": 2, "R3": 3, "G1": 2, "G2": 3, "G3": 4,
    "M1": 5, "M2": 6, "P": 7, "D1": 8, "D2": 9, "D3": 10, "N1": 9,
    "N2": 10, "N3": 11, "D": 8
}

class TranspositionEngine:
    @staticmethod
    def transpose(swaras: list, tonic: str, scale_type: str = "arohana") -> list:
        """
        Transposes a list of Carnatic swaras to absolute semitone offsets and Western note names
        relative to the given tonic.
        Returns:
            list of dicts, e.g. [{"swara": "S", "semitone": 0, "note": "C"}, ...]
        """
        tonic = tonic.upper().strip()
        if tonic not in NOTE_TO_SEMITONE:
            tonic = "C"  # default fallback
        tonic_offset = NOTE_TO_SEMITONE[tonic]

        result = []
        
        # 1. Choose octave starting value based on direction
        if scale_type == "avarohana":
            current_octave = 1
        else:
            current_octave = 0
            
        prev_base = -1

        for idx, swara in enumerate(swaras):
            # Clean symbols like S' or R2*
            clean_swara = re.sub(r"[^\w]", "", swara).strip()
            base_offset = SWARA_TO_SEMITONE_OFFSET.get(clean_swara, 0)

            if idx > 0:
                if scale_type == "avarohana":
                    # Descending boundary: base_offset jumps up significantly (e.g. S (0) to N3 (11))
                    if base_offset - prev_base > 8:
                        current_octave -= 1
                    elif clean_swara == "S" and idx == len(swaras) - 1:
                        current_octave = 0
                else:
                    # Ascending boundary: base_offset drops significantly (e.g. N3 (11) to S (0))
                    if base_offset - prev_base < -8:
                        current_octave += 1
                    elif clean_swara == "S" and prev_base >= 7:
                        current_octave = max(current_octave, 1)

            abs_semitone = base_offset + 12 * current_octave
            midi_note = (tonic_offset + abs_semitone) % 12
            note_name = SEMITONE_TO_NOTE[midi_note]

            result.append({
                "swara": swara,
                "semitone": abs_semitone,
                "note": note_name
            })
            prev_base = base_offset

        return result
