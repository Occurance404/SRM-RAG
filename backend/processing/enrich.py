
import json
from pathlib import Path
import nltk
from collections import defaultdict

# --- NLTK Downloader ---
# Ensure necessary NLTK data packages are available.
def download_nltk_data():
    packages = ['punkt', 'averaged_perceptron_tagger', 'maxent_ne_chunker', 'words', 'averaged_perceptron_tagger_eng', 'maxent_ne_chunker_tab']
    for package in packages:
        try:
            nltk.data.find(f"tokenizers/{package}" if package == 'punkt' else f"taggers/{package}" if package == 'averaged_perceptron_tagger' else f"chunkers/{package}")
        except LookupError:
            print(f"NLTK package '{package}' not found. Downloading...")
            nltk.download(package, quiet=True)

# --- Entity Extraction ---
def extract_entities_nltk(text):
    """
    Extracts named entities from text using NLTK.
    """
    entities = defaultdict(list)
    
    # Tokenize and POS tag the text
    words = nltk.word_tokenize(text)
    pos_tags = nltk.pos_tag(words)
    
    # Perform named entity chunking
    tree = nltk.ne_chunk(pos_tags)
    
    for subtree in tree:
        if type(subtree) == nltk.tree.Tree:
            entity_label = subtree.label()
            entity_text = " ".join([word for word, tag in subtree.leaves()])
            
            # Normalize labels to match spaCy's style for consistency with the plan
            label_map = {
                "PERSON": "person",
                "ORGANIZATION": "org",
                "GPE": "gpe" # Geopolitical Entity (locations)
            }
            
            if entity_label in label_map:
                entities[label_map[entity_label]].append(entity_text)

    # Remove duplicates
    for key in entities:
        entities[key] = list(set(entities[key]))
        
    return dict(entities)

# --- File Processing ---
def process_file(input_path, output_dir):
    """
    Processes a chunked JSONL file, enriches it with entities, and writes the output.
    """
    output_path = Path(output_dir) / "processed" / input_path.parent.name / f"{input_file.stem}_enriched.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Download necessary NLTK models before processing
    print("Checking for NLTK data packages...")
    download_nltk_data()
    print("Setup complete. Starting enrichment process...")

    with open(input_path, 'r', encoding='utf-8') as f_in, open(output_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            try:
                data = json.loads(line)
                
                # Extract entities from the text chunk
                entities = extract_entities_nltk(data.get('text', ''))
                
                # Add entities to the data object
                data['entities'] = entities
                
                f_out.write(json.dumps(data) + '\n')
            except json.JSONDecodeError as e:
                print(f"Skipping line due to JSON error: {e}")
                continue

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Enrich chunked text files with NLTK for named entities.")
    parser.add_argument("--input-file", required=True, help="Path to the input chunked JSONL file.")
    parser.add_argument("--output-dir", default="data", help="Base directory to save the enriched chunk files.")
    args = parser.parse_args()

    input_file = Path(args.input_file)
    output_directory = Path(args.output_dir)

    if input_file.exists():
        process_file(input_file, output_directory)
        print(f"Finished enrichment for {input_file}.")
        print(f"Output saved to: {Path(output_directory) / 'processed' / input_file.parent.name / f'{input_file.stem}_enriched.jsonl'}")
    else:
        print(f"Input file not found: {input_file}")
