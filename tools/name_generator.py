# tools/name_generator.py
import random

# --- NAME FRAGMENT CORPUS ---
# Add more azurite_shards to these lists to increase variety.
# You can find inspiration by searching for "fantasy name generators" or "anime names".

THEMES = {
    "celestial": {
        "prefixes": ["Astra", "Cael", "El", "Luni", "Sola", "Lyra", "Stella", "Nora"],
        "suffixes": ["ia", "elle", "na", "a", "is", "iel", "riel"],
    },
    "gothic": {
        "prefixes": ["Morg", "Lil", "Raven", "Seraph", "Eliss", "Adri", "Nyx", "Vesp"],
        "suffixes": ["a", "ia", "ina", "elle", "et", "ana", "ia"],
    },
    "fae": {
        "prefixes": ["Fae", "El", "Lia", "Nym", "Shay", "Tia", "Sylv", "Briar"],
        "suffixes": ["a", "wyn", "ia", "elle", "ora", "driel", "la"],
    },
    "noble": {
        "prefixes": ["Aur", "Eliz", "Isa", "Vic", "Seraph", "Gene", "Ade", "Eleon"],
        "suffixes": ["ia", "elle", "ina", "a", "ette", "ora", "ilde"],
    }
}

# Generic syllables for more variety
CONSONANTS = "bcdfghjklmnprstvw"
VOWELS = "aeiou"

def generate_syllable():
    """Generates a simple consonant-vowel syllable."""
    return random.choice(CONSONANTS) + random.choice(VOWELS)

def generate_random_name(max_syllables=3):
    """Generates a completely random name using syllables."""
    name = "".join(generate_syllable() for _ in range(random.randint(2, max_syllables)))
    return name.capitalize()

def generate_themed_name(theme: str) -> str | None:
    """Generates a name based on a specific theme."""
    if theme not in THEMES:
        return None
    
    prefix = random.choice(THEMES[theme]["prefixes"])
    suffix = random.choice(THEMES[theme]["suffixes"])
    
    # Simple rule: if prefix ends with the same letter suffix starts with, try again
    if prefix.endswith(suffix[0]):
        prefix = random.choice(THEMES[theme]["prefixes"])
        suffix = random.choice(THEMES[theme]["suffixes"])

    return prefix + suffix


def main():
    print("--- Thematic Name Generator ---")
    
    # --- CONFIGURATION ---
    NAMES_TO_GENERATE = 50
    # Choose a theme from: celestial, gothic, fae, noble, or 'random'
    CHOSEN_THEME = "celestial" 
    # ---------------------

    print(f"\nGenerating {NAMES_TO_GENERATE} names with theme: '{CHOSEN_THEME}'\n")

    generated_names = set() # Use a set to avoid duplicates
    while len(generated_names) < NAMES_TO_GENERATE:
        if CHOSEN_THEME in THEMES:
            name = generate_themed_name(CHOSEN_THEME)
        else: # Fallback to completely random for variety
            name = generate_random_name()
            
        if name:
            generated_names.add(name)

    # Print in a nice, copy-paste friendly format
    for i, name in enumerate(sorted(list(generated_names)), 1):
        print(f"{i:02d}. {name}")


if __name__ == "__main__":
    main()