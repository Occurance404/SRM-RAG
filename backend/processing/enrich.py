
import json
from pathlib import Path
import spacy
from collections import defaultdict
import re

# --- SpaCy Model Loading ---
def load_spacy_model(model_name="en_core_web_sm"):
    """
    Loads a spaCy model, downloading it if necessary.
    """
    try:
        nlp = spacy.load(model_name)
    except OSError:
        print(f"spaCy model '{model_name}' not found. Downloading...")
        from spacy.cli import download
        download(model_name)
        nlp = spacy.load(model_name)
    return nlp

# --- Entity Extraction ---
def extract_entities_spacy(nlp, text):
    """
    Extracts named entities from text using spaCy.
    """
    doc = nlp(text)
    entities = defaultdict(list)
    for ent in doc.ents:
        entities[ent.label_.lower()].append(ent.text)
    
    # Remove duplicates
    for key in entities:
        entities[key] = list(set(entities[key]))

    return dict(entities)

# --- Page Typing ---
def get_page_type(url, headings):
    """
    Determines the page type based on URL and headings.
    """
    url = url.lower()
    heading_text = " ".join([h['text'].lower() for h in headings])

    if "faculty" in url or "people" in url or "directory" in url or "faculty" in heading_text:
        return "faculty"
    if "admission" in url or "apply" in url or "admission" in heading_text:
        return "admissions"
    if "news" in url or "event" in url or "news" in heading_text:
        return "news"
    return "other"

# --- Image Scoring ---
def score_image(image):
    """
    Calculates a quality score for an image.
    """
    score = 0.5 # Base score
    if image.get('alt'):
        score += 0.2
    if image.get('caption'):
        score += 0.2
    if "profile" in image.get('url', '').lower() or "faculty" in image.get('url', '').lower():
        score += 0.1
    return min(1.0, score)

# --- File Processing ---
def process_file(input_path, output_dir, nlp):
    """
    Processes a chunked JSONL file, enriches it with entities, and writes the output.
    """
    output_path = Path(output_dir) / "processed" / input_path.parent.name / f"{input_path.stem}_enriched.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, 'r', encoding='utf-8') as f_in, open(output_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            try:
                data = json.loads(line)
                
                # Enrich with entities
                entities = extract_entities_spacy(nlp, data.get('text', ''))
                data['entities'] = entities

                # Enrich with page type
                data['page_type'] = get_page_type(data.get('url', ''), data.get('headings', []))

                # Enrich images with scores
                if 'images' in data:
                    for image in data['images']:
                        image['quality_score'] = score_image(image)
                
                f_out.write(json.dumps(data) + '\n')
            except json.JSONDecodeError as e:
                print(f"Skipping line due to JSON error: {e}")
                continue


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Enrich chunked text files with spaCy for named entities.")
    parser.add_argument("--input-file", required=True, help="Path to the input chunked JSONL file.")
    parser.add_argument("--output-dir", default="data", help="Base directory to save the enriched chunk files.")
    parser.add_argument("--model", default="en_core_web_sm", help="spaCy model to use for NER.")
    args = parser.parse_args()

    input_file = Path(args.input_file)
    output_directory = Path(args.output_dir)

    # Load the spaCy model
    nlp_model = load_spacy_model(args.model)

    if input_file.exists():
        process_file(input_file, output_directory, nlp_model)
        print(f"Finished enrichment for {input_file}.")
        print(f"Output saved to: {Path(output_directory) / 'processed' / input_file.parent.name / f'{input_file.stem}_enriched.jsonl'}")
    else:
        print(f"Input file not found: {input_file}")

