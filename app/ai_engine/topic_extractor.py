import re

def extract_topics(text):
    """
    Extracts topics from text based on heuristic segmentation.
    This is a basic implementation. In a real scenario, this would use NLP.
    
    Strategies:
    1. Look for lines that look like headings (short, capitalised, or numbered).
    2. Split by double newlines if no clear headings found.
    """
    topics = []
    
    heading_pattern = re.compile(r'(?:^|\n)(\d+\.?\s+[A-Z][a-zA-Z\s]+|Chapter\s+\d+|Section\s+\d+)(?:\n|$)')
    
    parts = heading_pattern.split(text)
    
    if len(parts) > 1:
       
        current_topic = "Introduction"
        if parts[0].strip():
             topics.append({'name': current_topic, 'content': parts[0].strip()})
             
        for i in range(1, len(parts), 2):
            if i+1 < len(parts):
                heading = parts[i].strip()
                content = parts[i+1].strip()
                if content:
                     topics.append({'name': heading, 'content': content})
    else:
        paras = text.split('\n\n')
        chunk_size = 5 
        
        for i in range(0, len(paras), chunk_size):
            chunk = "\n\n".join(paras[i:i+chunk_size])
            if chunk.strip():
               
                first_line = chunk.strip().split('\n')[0][:50]
                topics.append({'name': f"Topic: {first_line}...", 'content': chunk})
                
    if not topics:
         topics.append({'name': 'General Content', 'content': text})
         
    return topics
