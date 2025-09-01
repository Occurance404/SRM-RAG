
import json
from pathlib import Path
import nltk
import re

# Download the 'punkt' tokenizer models if they don't exist
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    nltk.download('punkt')

def get_text_for_heading(text, headings, heading_index):
    """
    Extracts the text content under a specific heading.
    """
    start_heading = headings[heading_index]
    start_pos = text.find(start_heading['text'])
    if start_pos == -1:
        return ""

    end_pos = len(text)
    # Find the start of the next heading of the same or higher level
    for i in range(heading_index + 1, len(headings)):
        if headings[i]['level'] <= start_heading['level']:
            next_heading_pos = text.find(headings[i]['text'], start_pos)
            if next_heading_pos != -1:
                end_pos = next_heading_pos
                break
    
    return text[start_pos:end_pos]

def chunk_section(text, max_chunk_tokens=400, overlap_tokens=100):
    """
    Chunks a section of text by sentences with overlap.
    """
    sentences = nltk.sent_tokenize(text)
    if not sentences:
        return []

    chunks = []
    current_chunk_sentences = []
    current_chunk_tokens = 0

    for sentence in sentences:
        sentence_tokens = len(nltk.word_tokenize(sentence))
        
        if current_chunk_tokens + sentence_tokens > max_chunk_tokens and current_chunk_sentences:
            chunks.append(" ".join(current_chunk_sentences))
            
            # Create overlap
            overlap_sentence_count = 0
            tokens_in_overlap = 0
            for i in range(len(current_chunk_sentences) - 1, -1, -1):
                tokens_in_overlap += len(nltk.word_tokenize(current_chunk_sentences[i]))
                if tokens_in_overlap >= overlap_tokens:
                    break
                overlap_sentence_count += 1
            
            if overlap_sentence_count > 0:
                current_chunk_sentences = current_chunk_sentences[-overlap_sentence_count:]
            else:
                current_chunk_sentences = []

            current_chunk_tokens = sum(len(nltk.word_tokenize(s)) for s in current_chunk_sentences)

        current_chunk_sentences.append(sentence)
        current_chunk_tokens += sentence_tokens

    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))
        
    return chunks

def chunk_document(doc):
    """
    Chunks a document by headings, then sentences, with overlap.
    """
    text = doc.get('clean_text', '')
    headings = doc.get('headings', [])
    all_chunks = []
    
    if not headings:
        # If no headings, chunk the whole document
        text_chunks = chunk_section(text)
        for chunk in text_chunks:
            all_chunks.append({"text": chunk, "section_path": []})
        return all_chunks

    heading_stack = []
    for i, heading in enumerate(headings):
        while heading_stack and heading['level'] <= heading_stack[-1]['level']:
            heading_stack.pop()
        heading_stack.append(heading)
        
        section_text = get_text_for_heading(text, headings, i)
        if not section_text:
            continue

        section_chunks = chunk_section(section_text)
        for chunk in section_chunks:
            all_chunks.append({
                "text": chunk,
                "section_path": [h['text'] for h in heading_stack]
            })

    return all_chunks

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
                chunk_data_list = chunk_document(data)
                
                for i, chunk_data in enumerate(chunk_data_list):
                    chunk_text = chunk_data['text']
                    associated_images = []
                    if images: # Only search if there are images
                        for image in images:
                            # Check if context snippet exists and is in the chunk
                            if image.get('context_snippet') and image['context_snippet'] in chunk_text:
                                if image.get('url'):
                                    associated_images.append(image['url'])
                    
                    final_chunk = {
                        "chunk_id": f"{data['url']}-{i}",
                        "page_id": data.get('url'),
                        "url": data.get('url'),
                        "title": data.get('title'),
                        "text": chunk_text,
                        "section_path": chunk_data['section_path'],
                        "images": associated_images,
                    }
                    f_out.write(json.dumps(final_chunk) + '\n')
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
