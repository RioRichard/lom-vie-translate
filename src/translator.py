import itertools
import google.generativeai as genai
import asyncio
import time
from threading import Lock
from src.config import API_KEYS, PRIMARY_LLM_MODEL, FALLBACK_LLM_MODELS, RATE_LIMIT_IF_QUOTA_EXCEEDED
from src.logger import logger

# Thread safety for API key rotation
api_key_lock = Lock()

# Initialize API key rotation
api_key_cycle = itertools.cycle(API_KEYS)

generation_config = {
    "temperature": 0,
    "max_output_tokens": 1000,
    "top_p": 1,
    "top_k": 1
}
def get_model(model_name):
    """Get a model instance with thread-safe API key rotation for a specific model_name"""
    with api_key_lock:
        next_api_key = next(api_key_cycle)
        api_index = API_KEYS.index(next_api_key) if next_api_key in API_KEYS else -1

    genai.configure(api_key=next_api_key)
    return genai.GenerativeModel(model_name, generation_config=generation_config), next_api_key, api_index

async def translate_text(text, thread_idx=None, name=None, prompt_data=None, name_to_translated=None, original_to_translated=None):
    global api_key_cycle
    from src.utils import postprocess_text
    from src.glossary import get_translated_by_name, find_original_matches

    # If no prompt_data provided, fall back to basic glossary lookup
    if not prompt_data:
        if name and name_to_translated:
            glossary_result = get_translated_by_name(name, name_to_translated)
            if glossary_result:
                logger.debug(f"Glossary match by name: {name} -> {glossary_result}")
                return glossary_result
        if original_to_translated:
            glossary_matches = find_original_matches(text, original_to_translated)
            if glossary_matches:
                logger.debug(f"Glossary matches found: {glossary_matches}")

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

    all_available_models = [PRIMARY_LLM_MODEL] + FALLBACK_LLM_MODELS
    MAX_GLOBAL_RETRIES = 1 # One additional full cycle retry
    global_retry_count = 0

    while global_retry_count <= MAX_GLOBAL_RETRIES:
        current_model_idx = 0
        while current_model_idx < len(all_available_models):
            current_model_name = all_available_models[current_model_idx]
            max_api_retries = len(API_KEYS)
            api_retries = 0

            while api_retries < max_api_retries:
                try:
                    model_instance, api_key, api_index = get_model(current_model_name)
                    logger.api_call(api_index, api_key, current_model_name)
                    logger.translation_start(name, text, current_model_name)
                    line_start = time.time()
                    response = await asyncio.to_thread(model_instance.generate_content, prompt)
                    line_end = time.time()
                    duration = line_end - line_start

                    if response.parts:
                        translated = response.text.strip()
                        translated = postprocess_text(translated)
                        logger.translation_output(translated, duration, current_model_name)
                        return translated
                    else:
                        logger.debug("Empty response received")
                        logger.translation_output("", duration, current_model_name)
                        api_retries += 1
                        if api_retries < max_api_retries:
                            logger.info(f"Retrying with next API key for Model {current_model_name} (Attempt {api_retries + 1}/{max_api_retries})")
                        else:
                            logger.warning(f"All API keys exhausted for Model {current_model_name}. Switching to next fallback model.")
                            current_model_idx += 1  # Move to the next model
                            # Reset API key cycle for the new model to start fresh
                            with api_key_lock:
                                pass # Removed api_key_cycle reset here
                            break  # Break from API key retry loop to try next model

                except Exception as e:
                    logger.error(f"Translation error with Model {current_model_name} and API key {api_index}: {str(e)}")
                    api_retries += 1
                    if api_retries < max_api_retries:
                        logger.info(f"Retrying with next API key for Model {current_model_name} (Attempt {api_retries + 1}/{max_api_retries})")
                    else:
                        logger.warning(f"All API keys exhausted for Model {current_model_name}. Switching to next fallback model.")
                        current_model_idx += 1  # Move to the next model
                        # Reset API key cycle for the new model to start fresh
                        with api_key_lock:
                            pass # Removed api_key_cycle reset here
                        break  # Break from API key retry loop to try next model

        # If we reach here, all models and API keys have been exhausted for the current global retry cycle
        if global_retry_count < MAX_GLOBAL_RETRIES:
            logger.info(f"All models and API keys exhausted. Initiating global retry {global_retry_count + 1}/{MAX_GLOBAL_RETRIES + 1} after delay.")
            await asyncio.sleep(RATE_LIMIT_IF_QUOTA_EXCEEDED)
            global_retry_count += 1
            # Reset API key cycle for the new global retry to start fresh
            with api_key_lock:
                api_key_cycle = itertools.cycle(API_KEYS)
        else:
            # All global retries exhausted
            break

    logger.critical("All models and API keys failed after all retries. Please check your configurations. Returning original text.")
    return text
