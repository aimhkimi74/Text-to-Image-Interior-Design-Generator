import os
import torch
from transformers import BertTokenizer, BertForSequenceClassification, BertConfig
import re
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------
# Device setup
# -----------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using device: {device}")

# -----------------------
# Model directory (from env or default)
# -----------------------
MODEL_DIR = os.getenv("BERT_MODEL_DIR", "models/bert")

# -----------------------
# Load tokenizer & model
# -----------------------
config = BertConfig.from_pretrained(MODEL_DIR)
tokenizer = BertTokenizer.from_pretrained(MODEL_DIR)
model = BertForSequenceClassification.from_pretrained(MODEL_DIR, config=config)
model.to(device)
model.eval()
logger.info(f"✅ Model loaded with {model.config.num_labels} labels (expected 7)")

# -----------------------
# Label mapping
# -----------------------
label_map = {
    0: "coastal",
    1: "industrial",
    2: "mid-century_modern",
    3: "modern",
    4: "rustic",
    5: "scandinavian",
    6: "traditional",
}

STYLE_HINTS = {
        'Modern': {
        'colors': ['graphite gray', 'beige', 'chrome', 'matte black', 'cool taupe','matte silver', 'deep charcoal', 'slate blue', 'steel blue', 'cool gray'],
        'furniture': ['sleek sofa', 'minimalist glass table', 'contemporary armchair', 'floating entertainment unit','platform media unit', 'slim sideboard', 'glass console table', 'modular sectional','low-profile couch', 'tempered glass table', 'metal-framed chairs','wall-mounted cabinet', 'pivoting TV stand'],
        'materials': ['carbon fiber', 'metal', 'high-gloss acrylic', 'concrete', 'smart fabric', 'polished wood','brushed steel', 'engineered wood', 'lacquered finish', 'tempered glass','high-gloss laminate', 'smoked glass', 'matte aluminum'],
        'lighting': ['recessed lighting', 'LED strips', 'track-integrated LEDs', 'smart panel lighting','track lighting', 'cove lighting', 'minimalist chandelier', 'spotlights','wall-mounted LEDs', 'strip lighting behind panels', 'angular sconces','indirect lighting'],
        'features': ['frameless cabinets', 'linear geometric accents', 'AI-controlled systems', 'large windows','motion lighting','minimal decoration', 'smart home tech', 'hidden storage', 'glass partitions','tech-integrated walls', 'framed abstract art', 'floor-to-ceiling panels','built-in climate control', 'seamless cabinetry'],
        'layout': ['zoned open-plan layout', 'balanced modern arrangement', 'clutter-free design','zoned space', 'linear flow', 'central focal point', 'multi-use open concept','asymmetrical furniture grouping', 'floating layout zones', 'expansive seating area']
    },
        'Industrial': {
        'colors': ['charcoal', 'rust', 'black', 'brown', 'steel gray', 'raw concrete'],
        'furniture': ['pipe-framed seating', 'metal-top coffee cart', 'factory cart', 'pipe shelving', 'vintage cabinet', 'industrial bench', 'steel wheel table', 'rolling stools', 'drafting desk'],
        'materials': ['exposed brick', 'riveted iron panels', 'reclaimed wood', 'grease-stained steel', 'iron', 'weathered leather', 'copper accents', 'metal mesh', 'galvanized pipe'],
        'lighting': ['Edison bulbs', 'metal pendant lights', 'factory lamps', 'exposed conduit lighting', 'industrial sconces', 'wire cage lighting', 'pulley fixtures', 'warehouse chandelier'],
        'features': ['exposed pipes', 'high ceilings', 'metal fixtures', 'concrete floors', 'open shelving', 'raw textures', 'rolling doors', 'unfinished surfaces', 'gear decor'],
        'layout': ['loft-style openness', 'open floor plan', 'exposed beams', 'spacious interior', 'minimalist storage', 'zoned workspaces', 'gallery-style walls']
    },
        'Scandinavian': {
        'colors': ['white', 'light gray', 'pale blue', 'mint green', 'pastel shades', 'soft beige', 'clay pink'],
        'furniture': ['simple sofa', 'wooden armchair', 'light oak table', 'open wood shelving', 'minimalist media unit', 'simple storage units', 'bean bag chair', 'slim writing desk', 'linen bench'],
        'materials': ['light wood', 'wool', 'cotton', 'natural fibers', 'white painted surfaces', 'felt', 'bamboo', 'linen blends', 'oak veneer'],
        'lighting': ['natural light', 'simple hanging lights', 'modern sconces', 'minimal floor lamps', 'white ceiling lights', 'skylights', 'clean-lined table lamps', 'LED bulbs', 'paper lanterns'],
        'features': ['minimal decor', 'plants', 'natural textures', 'functional design', 'light wood floors', 'modular furniture', 'sculptural art pieces', 'handwoven baskets', 'wall pegs', 'textile accents'],
        'layout': ['airy modular layout', 'clean lines and symmetry', 'focus on functionality', 'relaxing furniture arrangement', 'adjustable layouts', 'multi-purpose spaces', 'natural light maximization']
    },
        'Rustic': {
        'colors': ['warm brown', 'pine green', 'deep red', 'eggshell', 'raw timber', 'burnt orange', 'amber', 'moss green', 'bark gray'],
        'furniture': ['leather sofa', 'log slab table', 'rocking chair', 'barn wood shelves', 'vintage trunk', 'antique armchairs', 'aged timber bench', 'pine dining table', 'handcrafted stools'],
        'materials': ['aged timber', 'stone', 'natural linen', 'wrought iron', 'natural textiles', 'ceramic', 'burlap', 'rough cotton'],
        'lighting': ['wrought iron chandelier', 'lantern style lights', 'wooden beam lighting', 'iron wall sconces', 'candlelight', 'antique lamps', 'mason jar lamps'],
        'features': ['exposed beams', 'stone fireplace', 'wooden floors', 'vintage decor', 'raw nature accents', 'woven baskets', 'tree branch sculptures', 'log mantels', 'hand-hewn finishes'],
        'layout': ['central fireplace focus', 'country-style furniture', 'relaxed seating arrangement', 'emphasis on natural warmth', 'open kitchen area', 'family-friendly design', 'rug-centered layout']
    },
        'Traditional': {
        'colors': ['burgundy', 'navy', 'forest green', 'cream', 'gold', 'taupe', 'mahogany', 'warm beige', 'dark wood tones', 'rich brown', 'royal blue', 'antique white', 'bronze', 'sage green', 'chocolate brown'],
        'furniture': ['rolled arm sofa', 'ornate wood table', 'wingback chairs', 'mahogany sideboard', 'formal dining chairs', 'cabriole legs', 'tufted ottoman', 'claw-foot table', 'Queen Anne chairs', 'carved wood console', 'chesterfield sofa', 'bergère chair', 'secretary desk', 'china cabinet', 'upholstered bench'],
        'materials': ['dark woods', 'silk', 'damask fabrics', 'cherry wood', 'velvet', 'marble', 'embossed leather', 'brocade', 'walnut wood', 'embroidered fabrics', 'taffeta', 'oriental rugs', 'brass hardware', 'crystal accents', 'polished bronze'],
        'lighting': ['crystal chandeliers', 'wall sconces', 'table lamps with shades', 'brass fixtures', 'ornate ceiling fixtures', 'candelabra lights', 'tiffany lamps', 'pleated shade lamps', 'gilded floor lamps', 'library reading lamps'],
        'features': ['crown molding', 'arched doorways', 'wainscoting', 'drapery panels', 'fireplace mantels', 'antique accents', 'ceiling medallions', 'built-in bookcases', 'decorative pillars', 'tray ceilings', 'picture frame molding', 'oriental carpets', 'oil paintings', 'gilt mirrors', 'carved woodwork'],
        'layout': ['symmetrical layout', 'formal arrangement', 'central fireplace or artwork focus', 'defined conversation zones', 'grand entrance focus', 'balanced furniture pairs', 'formal dining setup', 'classical proportions']
    },
        'Mid-Century Modern': {
        'colors': ['mustard', 'olive green', 'burnt orange', 'aqua', 'walnut brown', 'off-white', 'teal blue', 'harvest gold', 'avocado green', 'tangerine', 'mocha brown', 'seafoam green', 'dusty rose', 'earthy terracotta', 'sage green', 'warm gray', 'deep turquoise', 'muted coral'],
        'furniture': ['Eames lounge chair', 'tapered leg sofa', 'organic teak table', 'credenza', 'arc floor lamp', 'tulip chair', 'egg chair', 'butterfly chair', 'danish sideboard', 'sculptural dining table', 'molded plastic chairs', 'floating cabinet', 'platform bench', 'womb chair', 'bar cart', 'shell chairs'],
        'materials': ['walnut veneer', 'teak', 'tanned leather', 'brass', 'fiberglass', 'glass', 'rosewood', 'bent plywood', 'molded plastic', 'chrome', 'patterned vinyl', 'brushed steel', 'oak veneer', 'aluminum', 'textured upholstery', 'stainless steel', 'cork'],
        'lighting': ['tripod lamps', 'sputnik chandeliers', 'globe pendants', 'mod floor lamps', 'atomic sconces', 'starburst fixtures', 'mushroom lamps', 'geometric pendants', 'bubble lamps', 'cone wall sconces', 'space-age lighting', 'sculptural desk lamps', 'brass accent lights'],
        'features': ['sunken rooms', 'wall paneling', 'modular storage', 'built-ins', 'abstract art', 'geometric patterns', 'floating fireplaces', 'conversation pits', 'room dividers', 'wood slat walls', 'terrazzo floors', 'graphic wallpaper', 'atomic motifs', 'indoor planters', 'statement clocks', 'period artwork'],
        'layout': ['low-profile open design', 'accent-walled zones', 'natural light centered design', 'split-level layout', 'indoor-outdoor flow', 'angular divisions', 'conversation areas', 'minimal space planning', 'layered lighting', 'floating room dividers']
    },
        'Coastal': {
        'colors': ['ocean blue', 'sandy beige', 'seafoam green', 'pearl white', 'coral pink', 'light gray', 'turquoise', 'navy blue', 'driftwood gray', 'shell pink', 'aqua', 'sea glass green', 'warm sand', 'pale yellow', 'coastal fog', 'azure blue', 'beach grass green'],
        'furniture': ['slipcovered sofa', 'wicker armchair', 'nautical center table', 'rattan seating', 'bamboo console', 'adirondack chair', 'rope accent chair', 'weathered bench', 'seagrass ottoman', 'white media cabinet', 'woven side tables', 'driftwood furniture', 'coastal storage unit', 'beach house sectional', 'wicker trunk', 'bamboo screen'],
        'materials': ['wicker', 'rattan', 'seagrass', 'whitewashed wood', 'jute', 'linen canvas', 'cotton canvas', 'weathered wood', 'rope', 'woven bamboo', 'sisal', 'distressed wood', 'natural fiber', 'painted wood', 'bleached wood', 'grasscloth', 'sea glass'],
        'lighting': ['rope pendant lights', 'coastal chandeliers', 'woven basket lights', 'glass bottle lamps', 'driftwood sconces', 'nautical wall lights', 'capiz shell fixtures', 'lantern lights', 'rattan pendants', 'seagrass shade lamps', 'fisherman lights', 'shell fixtures', 'beach glass pendants'],
        'features': ['shiplap walls', 'weathered beams', 'coastal artwork', 'shell collections', 'nautical accessories', 'beach-themed decor', 'ocean view windows', 'rope accents', 'natural fiber rugs', 'striped textiles', 'driftwood accents', 'coral displays', 'coastal weave baskets', 'seaside photographs', 'maritime antiques'],
        'layout': ['breezy open-concept', 'indoor-outdoor flow', 'panoramic windows', 'casual seating groups', 'light-filled rooms', 'relaxed furniture placement', 'outdoor living connection', 'beachfront orientation', 'informal gathering spaces', 'wraparound seating']
    }
}

def extract_keywords_from_styles(style_hints):
    extracted = {}
    for style, categories in style_hints.items():
        keywords = []
        for values in categories.values():
            keywords.extend(values)
        extracted[style.lower()] = list(set(keywords))  # Remove duplicates
    return extracted

STYLE_KEYWORDS = extract_keywords_from_styles(STYLE_HINTS)


def is_living_room_related(prompt):
    """Check if the prompt contains living room related terms."""
    living_room_terms = [
        r'\bliving\s*room\b', r'\bsitting\s*room\b', r'\blounge\b', r'\bfamily\s*room\b',
        r'\bliving\s*area\b', r'\bsitting\s*area\b', r'\bcommon\s*area\b', r'\bfront\s*room\b',
        r'\bparlor\b', r'\bden\b', r'\bgreat\s*room\b', r'\breception\s*room\b'
    ]
    prompt_lower = prompt.lower()
    return any(re.search(term, prompt_lower) for term in living_room_terms)

def sanitize_prompt(prompt):
    """Basic sanitization of prompt input."""
    if not prompt or not isinstance(prompt, str):
        return ""
    # Remove leading/trailing whitespace and multiple spaces
    cleaned = ' '.join(prompt.strip().split())
    return cleaned

def validate_prompt_locally(prompt):
    prompt = sanitize_prompt(prompt)
    logger.info(f"Validating prompt: '{prompt}'")

    if not prompt:
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "style_confidence": 0.0,
            "intent": "invalid",
            "style_reasons": [],
            "message": "Prompt is empty."
        }

    if not is_living_room_related(prompt):
        logger.warning(f"Prompt rejected for not related to living room: '{prompt}'")
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "style_confidence": 0.0,
            "intent": "invalid",
            "style_reasons": [],
            "message": "Prompt must be related to living room design."
        }

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            # Boost logits based on keyword matches
            KEYWORD_BOOST = 0.5
            LABEL_EXPLICIT_BOOST = 2.0
            lower_prompt = prompt.lower()
            for i, label in label_map.items():
                style_lower = label.lower()
                keywords = STYLE_KEYWORDS.get(style_lower, [])
                
                match_keywords = [k for k in keywords if k.lower() in lower_prompt]
                if match_keywords:
                    logits[0][i] += KEYWORD_BOOST
                    logger.info(f"📌 Boosted '{label}' for keyword match: {match_keywords}")
                
                if label.replace("_", " ") in lower_prompt:
                    logits[0][i] += LABEL_EXPLICIT_BOOST
                    logger.info(f"📣 Explicit style mention of '{label}' — stronger boost applied.")

            # Penalize rustic if it's not explicitly mentioned or matched by keywords
            rustic_idx = next((i for i, l in label_map.items() if l.lower() == "rustic"), None)
            if rustic_idx is not None:
                rustic_keywords = STYLE_KEYWORDS["rustic"]
                if "rustic" not in lower_prompt and not any(k in lower_prompt for k in rustic_keywords):
                    logits[0][rustic_idx] -= 1.0  # adjust as needed
                    logger.info("⛔ Penalized 'rustic' due to lack of matching indicators.")

            if logits is None or logits.shape[0] == 0:
                logger.error("Model returned empty logits.")
                raise ValueError("Invalid model output")

            # Only allow these styles for UI use
            ALLOWED_STYLES = ["modern", "scandinavian", "industrial", "coastal", "mid-century", "rustic", "traditional"]

            # Softmax over all logits first
            probs = torch.nn.functional.softmax(logits, dim=1)[0]

            # 🔍 Optional log
            full_sorted = list(enumerate(probs.tolist()))
            full_sorted.sort(key=lambda x: x[1], reverse=True)
            original_top_idx, original_top_conf = full_sorted[0]
            original_top_label = label_map.get(original_top_idx, "unknown")
            if original_top_label not in ALLOWED_STYLES:
                logger.info(f"🔍 Top model prediction '{original_top_label}' ({original_top_conf:.3f}) excluded from allowed UI styles")

            # Extract only allowed logits
            allowed_indices = [idx for idx, label in label_map.items() if label in ALLOWED_STYLES]
            filtered = [(idx, probs[idx].item()) for idx in allowed_indices]
            filtered.sort(key=lambda x: x[1], reverse=True)
            top1_idx, top1_conf = filtered[0]
            top2_idx, top2_conf = filtered[1]

            # Override top style with explicitly mentioned style if confidence is close
            explicit_mentioned_idx = None
            for i, label in label_map.items():
                if label.replace("_", " ") in lower_prompt:
                    explicit_mentioned_idx = i
                    break

            if explicit_mentioned_idx is not None and explicit_mentioned_idx != top1_idx:
                gap = probs[top1_idx].item() - probs[explicit_mentioned_idx].item()
                if gap < 0.1:  # adjustable threshold
                    logger.warning(f"⚠️ Overriding top style to explicitly mentioned '{label_map[explicit_mentioned_idx]}' due to close confidence margin.")
                    top1_idx = explicit_mentioned_idx
                    top1_conf = probs[explicit_mentioned_idx].item()

            logger.info("🧠 Full style prediction breakdown:")
            for i, prob in enumerate(probs):
                logger.info(f" - {label_map[i]}: {prob:.4f}")

        style_name = label_map.get(top1_idx, "unknown")
        second_style = label_map.get(top2_idx, "unknown")
        logger.info(f"Predicted style: {style_name} ({top1_conf:.3f}), 2nd: {second_style} ({top2_conf:.3f})")
        if "modern" in lower_prompt and style_name != "modern":
            logger.warning(f"⚠️ User mentioned 'modern' but predicted style is '{style_name}'")

        explanation = []
        lower_prompt = prompt.lower()
        style_title_case = style_name.title()  # convert 'modern' → 'Modern'

        # Only try to explain if it's a recognized style
        if style_title_case in STYLE_HINTS:
            matched_categories = []
            for category, keywords in STYLE_HINTS[style_title_case].items():
                for keyword in keywords:
                    if keyword.lower() in lower_prompt:
                        matched_categories.append(category)
                        explanation.append(f"mentions of {category} like '{keyword}'")
                        break  # avoid listing the same category multiple times
            if not matched_categories:
                explanation.append("based on overall language and style structure")
        else:
            explanation.append("style not found in hint database")
        logger.info(f"💡 Matched categories for explanation: {matched_categories}")

        return {
            "valid": True,
            "prompt_score": round(top1_conf, 3),
            "detected_style": style_name,
            "style_confidence": round(top1_conf, 3),
            "secondary_style": second_style,
            "secondary_confidence": round(top2_conf, 3),
            "intent": "generate",
            "style_reasons": explanation,
            "message": "Prompt validation completed"
        }

    except Exception as e:
        logger.exception("Error during prompt validation")
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "style_confidence": 0.0,
            "intent": "invalid",
            "style_reasons": [],
            "message": f"Validation error: {str(e)}"
        }

def validate_prompt_simple(prompt):
    prompt = sanitize_prompt(prompt)
    logger.info(f"Simple validation of prompt: '{prompt}'")

    if not prompt:
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "prompt": prompt,
            "message": "Prompt is empty."
        }

    if not is_living_room_related(prompt):
        logger.warning(f"Prompt rejected for not related to living room: '{prompt}'")
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "prompt": prompt,
            "message": "Prompt must be related to living room design."
        }

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits

            if logits is None or logits.shape[0] == 0:
                logger.error("Model returned empty logits.")
                raise ValueError("Invalid model output")

            probs = torch.nn.functional.softmax(logits, dim=1)
            sorted_probs = list(enumerate(probs[0].tolist()))
            sorted_probs.sort(key=lambda x: x[1], reverse=True)
            top1_idx, top1_conf = sorted_probs[0]
            style_name = label_map.get(top1_idx, "unknown")
            is_valid = top1_conf >= 0.5

        return {
            "valid": is_valid,
            "prompt_score": round(top1_conf, 3),
            "detected_style": style_name if is_valid else "unknown",
            "prompt": prompt,
            "message": "Prompt validation completed" if is_valid else "Prompt rejected by confidence threshold"
        }

    except Exception as e:
        logger.exception("Error during simple prompt validation")
        return {
            "valid": False,
            "prompt_score": 0.0,
            "detected_style": "unknown",
            "prompt": prompt,
            "message": f"Validation error: {str(e)}"
        }

def format_bot_message(result):
    style = result.get("detected_style", "unknown").title()
    confidence = int(result.get("style_confidence", 0) * 100)
    secondary = result.get("secondary_style", "")
    secondary_conf = int(result.get("secondary_confidence", 0) * 100)
    reasons = result.get("style_reasons", [])

    lines = [
        f"**🧠 Style Detection Result**",
        f"**Detected Style:** `{style}` (Confidence: **{confidence}%**)"
    ]
    if secondary and secondary != style.lower():
        lines.append(f"**Runner-Up Style:** `{secondary.title()}` (Confidence: **{secondary_conf}%**)")

    if reasons:
        lines.append("\n**Why this style was selected:**")
        for i, reason in enumerate(reasons, 1):
            lines.append(f"{i}. ✅ {reason.capitalize()}")

    return "\n".join(lines)

# Optional: run a dummy prediction once on import to warm up model
#try:
    #logger.info("Warming up model with dummy prompt...")
    #validate_prompt_locally("A modern living room with wooden furniture and natural light.")
    #logger.info("Model warm-up complete.")
#except Exception as e:
    #logger.error(f"Warm-up failed: {e}")
