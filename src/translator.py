import itertools
import google.generativeai as genai
import time
from threading import Lock
from src.config import API_KEYS, GOOGLE_STUDIO_AI_LLM, RATE_LIMIT_IF_QUOTA_EXCEEDED
from src.logger import logger

# Thread safety for API key rotation
api_key_lock = Lock()

# Initialize API key rotation
api_key_cycle = itertools.cycle(API_KEYS)

# Model configuration
generation_config = {
    "temperature": 0,    # Most consistent output
    "max_output_tokens": 1000,
    "top_p": 1,
    "top_k": 1
}
def get_model():
    """Get a model instance with thread-safe API key rotation"""
    with api_key_lock:
        next_api_key = next(api_key_cycle)
        api_index = API_KEYS.index(next_api_key) if next_api_key in API_KEYS else -1

    genai.configure(api_key=next_api_key)
    return genai.GenerativeModel(GOOGLE_STUDIO_AI_LLM, generation_config=generation_config), next_api_key, api_index

def translate_text(text, thread_idx=None, name=None, prompt_data=None, name_to_translated=None, original_to_translated=None):
    from src.utils import postprocess_text, special_chars
    from src.grossary import get_translated_by_name, find_original_matches

    # Handle special characters and glossary lookups
    if text.strip() in special_chars or text in special_chars:
        logger.debug(f"Special character found: {text.strip()}")
        return text.strip()

    # If no prompt_data provided, fall back to basic glossary lookup
    if not prompt_data:
        if name and name_to_translated:
            grossary_result = get_translated_by_name(name, name_to_translated)
            if grossary_result:
                logger.debug(f"Glossary match by name: {name} -> {grossary_result}")
                return grossary_result
        if original_to_translated:
            grossary_matches = find_original_matches(text, original_to_translated)
            if grossary_matches:
                logger.debug(f"Glossary matches found: {grossary_matches}")

    # Use prepared prompt if available, otherwise use default translation prompt
    if prompt_data and 'prompt' in prompt_data:
        prompt = prompt_data['prompt']
    else:
        # Default translation prompt
        prompt = f"""
Bạn là một chuyên gia dịch thuật từ Tiếng Trung (Giản thể) sang Tiếng Việt.
Bối cảnh: Đây là một phần của câu chuyện trong tựa game Legend of Mortal.
Nhiệm vụ của bạn là:
1. Dịch từ Tiếng Trung (Giản thể) sang Tiếng Việt.
2. Đảm bảo câu văn trở tự nhiên, mượt mà và đúng ngữ pháp.
3. Tự động phát hiện và viết hoa đúng các danh từ riêng (tên người, địa danh, tổ chức, v.v.)....
4. Giữ nguyên ý nghĩa ban đầu của câu văn. Không cần phải giải thích thêm ý nghĩa của câu văn.
5. Phong cách kiếm hiệp
6. Giữ nguyên các kí hiệu đánh dấu đặc biệt như [|], [||], ???, ???, {{title}}, [{{0}}], v.v....
7. Trong trường hợp văn bản gốc chỉ có dấu đặc biệt hoặc rỗng, trả về y hệt và không giải thích hay yêu cầu gì thêm.
8. Chỉ trả về phần văn bản đã được dịch.

**Văn bản cần được dịch:**
{text}
"""
    logger.debug(f"Using prompt:\n{prompt}")
    max_retries = len(API_KEYS)
    retries = 0
    while retries < max_retries:
        try:
            model, api_key, api_index = get_model()
            logger.api_call(api_index, api_key)
            logger.translation_start(name, text)

            line_start = time.time()
            response = model.generate_content(prompt)
            line_end = time.time()
            duration = line_end - line_start

            if response.parts:
                translated = response.text.strip()
                translated = postprocess_text(translated)
                logger.translation_output(translated, duration)
                return translated

            logger.debug("Empty response received")
            logger.translation_output("", duration)
            return ""

        except Exception as e:
            logger.error(f"Translation error with API key {api_index}: {str(e)}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying with next API key (Attempt {retries + 1}/{max_retries})")
                time.sleep((RATE_LIMIT_IF_QUOTA_EXCEEDED)/(max_retries-retries))
            else:
                logger.error("All API keys failed. Returning original text.")
                return text
    return text
