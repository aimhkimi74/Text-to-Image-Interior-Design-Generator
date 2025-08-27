import requests
import logging
import json
import time
from flask import current_app, has_app_context
from .bert_validation import validate_prompt_locally

logger = logging.getLogger(__name__)


class BackendService:
    def __init__(self, app=None):
        self.app = app
        self.use_local_validation = False
        self.base_url = None

        if app:
            self.init_app(app)

    def init_app(self, app):
        # Enable local BERT if configured
        self.use_local_validation = app.config.get("USE_LOCAL_BERT", False)
        if self.use_local_validation:
            logger.info("✅ Using local BERT validation")

        # Always configure base_url for remote image generation
        backend_url = app.config.get("COLAB_ENDPOINT", "").rstrip("/")
        if backend_url:
            self.base_url = backend_url
            logger.info(f"✅ Colab endpoint set for image generation: {self.base_url}")

            if not self._test_connection():
                logger.error("❌ Failed to connect to backend service at COLAB_ENDPOINT")
                return False
        else:
            self.base_url = None
            logger.warning("⚠️ COLAB_ENDPOINT not configured — image generation will be disabled")

        return True

    def _ensure_base_url(self):
        """Ensure base_url is always up-to-date from app context if needed."""
        if not self.base_url and not self.use_local_validation:
            if self.app:
                self.init_app(self.app)
            elif has_app_context():
                self.init_app(current_app)

    def _test_connection(self):
        self._ensure_base_url()
        if not self.base_url:
            logger.warning("❌ Cannot test connection: Backend URL not configured")
            return False
        try:
            health_url = f"{self.base_url}/health"
            headers = {"ngrok-skip-browser-warning": "1"}
            response = requests.get(health_url, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info("✅ Backend health check passed")
                return True
            try:
                root_response = requests.get(self.base_url, headers=headers, timeout=10)
                if root_response.status_code == 200:
                    logger.info("✅ Backend root endpoint accessible")
                    return True
            except:
                pass
            logger.warning(f"⚠️ Backend health check failed with status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Backend health check error: {str(e)}")
        return False

    def _send_request(self, endpoint, payload, max_retries=3, retry_delay=2):
        self._ensure_base_url()
        if not self.base_url:
            logger.error("❌ Backend URL not configured")
            return None, "Backend URL not configured"

        full_url = f"{self.base_url}{endpoint}"

        # Safer logging: only preview part of payload
        try:
            payload_preview = json.dumps(payload)[:200] + (
                "..." if len(json.dumps(payload)) > 200 else ""
            )
        except Exception:
            payload_preview = str(payload)[:200] + "..."
        logger.debug(f"➡️ Sending request to: {full_url}")
        logger.debug(f"📝 Payload preview: {payload_preview}")

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    full_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "ngrok-skip-browser-warning": "1",
                    },
                    timeout=60,
                )
                logger.info(f"⬅️ Response status: {response.status_code}")
                if response.status_code == 200:
                    return response.json(), None
                elif response.status_code == 429:
                    logger.warning(f"⏳ Rate limit exceeded (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    try:
                        error_msg = response.json().get(
                            "error", f"HTTP error {response.status_code}"
                        )
                    except:
                        error_msg = f"HTTP error {response.status_code}"
                    logger.error(f"❌ Request failed: {error_msg}")
                    return None, error_msg
            except requests.exceptions.Timeout:
                logger.warning(f"⏱️ Request timed out (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
            except Exception as e:
                logger.error(f"❌ Request error: {str(e)}")
                return None, str(e)

        return None, "Maximum retry attempts reached"

    def generate_image(
        self,
        prompt,
        style="modern",
        guidance_scale=7.5,
        negative_prompt=None,
        num_inference_steps=None,
        seed=None,
    ):
        self._ensure_base_url()

        if not self.base_url:
            logger.warning("⚠️ Skipping image generation: no backend URL configured")
            return None, "Image generation is disabled because COLAB_ENDPOINT is not configured or accessible."

        if not self._test_connection():
            logger.error("❌ Backend service unavailable")
            return None, "Backend service is currently unavailable. Please try again later."

        endpoint = "/generate"
        payload = {"prompt": prompt}

        if style and style != "auto":
            payload["style"] = style
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if guidance_scale:
            payload["guidance_scale"] = guidance_scale
        if num_inference_steps:
            payload["num_inference_steps"] = num_inference_steps
        if seed:
            payload["seed"] = seed

        # Safe logging for prompts
        prompt_preview = (prompt[:100] + "...") if len(prompt) > 100 else prompt
        logger.info(f"🖼️ Generating image with prompt preview: '{prompt_preview}'")

        result, error = self._send_request(endpoint, payload)

        if error:
            if "404" in str(error):
                logger.warning("⚠️ Backend returned 404 - likely missing route or misconfigured backend URL.")
            logger.error(f"❌ Image generation failed: {error}")
            return None, error

        # Handle base64 image fallback
        if not result.get("image_url") and result.get("image"):
            result["image_url"] = f"data:image/png;base64,{result['image']}"

        if not result.get("image_url"):
            logger.error("⚠️ No image data in response")
            return None, "No image data in response"

        return result, None

    def validate_prompt(self, prompt):
        if self.use_local_validation:
            try:
                result = validate_prompt_locally(prompt)
                logger.info("✅ Local prompt validation complete")
                return result, None
            except Exception as e:
                logger.error(f"❌ Local prompt validation error: {e}")
                return None, str(e)

        # Remote validation
        self._ensure_base_url()
        if not self.base_url:
            logger.error("❌ Backend URL not configured")
            return None, "Backend URL not configured"

        endpoint = "/validate_prompt"
        payload = {"prompt": prompt}

        prompt_preview = (prompt[:80] + "...") if len(prompt) > 80 else prompt
        logger.info(f"🧠 Validating prompt remotely: '{prompt_preview}'")

        try:
            result, error = self._send_request(endpoint, payload)

            if error:
                if "404" in str(error):
                    logger.warning("⚠️ Backend returned 404 - likely missing route or misconfigured backend URL.")
                logger.error(f"❌ Prompt validation failed: {error}")
                return None, error

            if result and "valid" in result:
                logger.info("✅ Prompt validation success")
                return result, None

            if result and "prompt_score" in result:
                adapted_result = {
                    "valid": result.get("prompt_score", 0) > 0.5,
                    "prompt_score": result.get("prompt_score", 0),
                    "detected_style": result.get("detected_style", "unknown"),
                    "style_confidence": result.get("style_confidence", 0),
                    "intent": result.get("intent", "ask"),
                    "enhanced_prompt": result.get("enhanced_prompt", prompt),
                    "style_reasons": result.get(
                        "style_reasons", ["Based on general design elements"]
                    ),
                    "message": result.get("message", "Prompt validation completed"),
                }
                logger.info("🔄 Adapted validation result generated")
                return adapted_result, None

            logger.warning(f"⚠️ Unexpected response format: {result}")
            return None, "Invalid response format from backend"

        except Exception as e:
            logger.exception(f"❌ Exception during prompt validation: {str(e)}")
            return None, f"Validation error: {str(e)}"

    def check_health(self):
        if not self.base_url:
            return False

        try:
            headers = {"ngrok-skip-browser-warning": "1"}
            response = requests.get(f"{self.base_url}/health", headers=headers, timeout=5)

            if response.status_code == 404:
                response = requests.get(self.base_url, headers=headers, timeout=5)

            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def is_offline_mode(self):
        if has_app_context():
            return current_app.config.get("OFFLINE_MODE", False)
        return False

    def process_pending_messages(self, session_id=None):
        if not self._test_connection():
            logger.info("Backend still unavailable, skipping pending message processing")
            return False, "Backend still unavailable"
        return True, "Processed pending messages"
