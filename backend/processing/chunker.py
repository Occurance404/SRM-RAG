
import json
from pathlib import Path
import nltk

# Download the 'punkt' tokenizer models if they don't exist
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    nltk.download('punkt')

def chunk_text_by_sentence(text, max_chunk_chars=1000):
    """
    Chunks text by sentences, grouping them into chunks of a max size.
    """
    sentences = nltk.sent_tokenize(text)
    
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 < max_chunk_chars:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    
    if current_chunk: # Add the last chunk
        chunks.append(current_chunk.strip())
        
    return chunks

def process_file(input_path, output_dir):
    """
    Processes a single JSONL file, chunks the text, and writes the output.
    """
    output_path = Path(output_dir) / "processed" / input_path.parent.name / f"{input_path.stem}_chunks.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, 'r', encoding='utf-8') as f_in, open(output_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            try:
                data = json.loads(line)
                images = data.get('images', [])
                text_chunks = chunk_text_by_sentence(data.get('clean_text', ''))
                
                for i, chunk in enumerate(text_chunks):
                    associated_images = []
                    if images: # Only search if there are images
                        for image in images:
                            # Check if context snippet exists and is in the chunk
                            if image.get('context_snippet') and image['context_snippet'] in chunk:
                                if image.get('url'):
                                    associated_images.append(image['url'])
                    
                    chunk_data = {
                        "chunk_id": f"{data['url']}-{i}",
                        "page_id": data.get('url'),
                        "url": data.get('url'),
                        "title": data.get('title'),
                        "text": chunk,
                        "section_path": [], # Placeholder for heading lineage
                        "images": associated_images,
                    }
                    f_out.write(json.dumps(chunk_data) + '\n')
            except json.JSONDecodeError as e:
                print(f"Skipping line due to JSON error: {e}")
                continue


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Chunk cleaned text files using NLTK.")
    parser.add_argument("--input-file", required=True, help="Path to the input JSONL file from the crawler.")
    parser.add_argument("--output-dir", default="data", help="Base directory to save the processed chunk files.")
    args = parser.parse_args()

    input_file = Path(args.input_file)
    output_directory = Path(args.output_dir)

    if input_file.exists():
        process_file(input_file, output_directory)
        print(f"Processed {input_file} and saved chunked output.")
    else:
        print(f"Input file not found: {input_file}")
