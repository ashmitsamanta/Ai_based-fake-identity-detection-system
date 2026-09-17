import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from utils.image_utils import (  # noqa: F401 — re-export
    cleanup_all_temp,
    cleanup_session_dir,
    create_session_temp_dir,
    read_image_cv2_safe,
    save_temp_upload,
    validate_image_file,
)
from utils.verhoeff import (  # noqa: F401 — re-export
    D_TABLE,
    P_TABLE,
    INV_TABLE,
    generate_check_digit,
    is_valid_aadhaar,
    validate_aadhaar,
    validate_pan,
    validate_vid,
)

