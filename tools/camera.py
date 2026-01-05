import cv2
import time
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from core.config import cfg as config
class Camera():
    def __init__(self, camera_index = 0, yaml_file = "config.yaml"):
        self.camera_index = camera_index

        self.model_name = config['LLM']['MODEL_NAME']
        # self.system_prompt = system_prompt
        self.base_url = config['LLM']['BASE_URL']
        self.api_key = config['LLM']['API_KEY']


    def capture_photo(self) -> str:
        """
        Captures a 720p photo with auto-exposure enabled (best quality on cheap webcams).
        Uses V4L2 on Linux and lightly optimizes noise + stability.
        """

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)

        if not cap.isOpened():
            return "ERROR: Camera failed to open."

        # ---------- Resolution ----------
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # ---------- Auto Exposure (ON — best quality) ----------
        # 3 = V4L2_EXPOSURE_APERTURE_PRIORITY (auto)
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)

        # ---------- Noise Reduction ----------
        # Lower gain reduces grain but keeps auto-exposure behavior
        cap.set(cv2.CAP_PROP_GAIN, 0)

        # Optional: set brightness slightly lower so auto exposure doesn't overcompensate
        cap.set(cv2.CAP_PROP_BRIGHTNESS, 0.2)

        # ---------- Auto Focus Settings (optional) ----------
        # Turn off autofocus to avoid hunting during capture
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        cap.set(cv2.CAP_PROP_FOCUS, 15)

        # Give the camera time to auto-adjust exposure + white balance
        time.sleep(2)

        frames = []
        start_time = time.time()
        while time.time() - start_time < 2:
            ret, frame = cap.read()
            if ret:
                frames.append(frame)

        cap.release()

        if not frames:
            return "ERROR: Could not read frames."

        stable_frame = frames[len(frames) // 2]

        path = "generated/user.jpg"
        cv2.imwrite(path, stable_frame)
        return path

    def encode_image_base64(self, image_path: str) -> str:
        """
        Reads an image from disk and returns a base64-encoded string
        suitable for LangChain multimodal messages.

        Returns:
            str: base64 string WITHOUT headers like "data:image/jpeg;base64,"
        """
        import base64

        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    
    def llm(self, prompt: str) -> str:
        """
        Captures a fresh photo from the configured camera and sends it to the LLM for analysis.

        This function initializes a `Camera` instance, triggers an immediate image capture
        using the system webcam (or any camera defined in the configuration), and then
        sends the newly captured image to the LLM along with the user's query. The model
        analyzes the image according to the instruction and returns a structured response.

        Args:
            query (str): A natural language instruction describing how the LLM should
                interpret, evaluate, or describe the captured image.

        Returns:
            dict: The LLM-generated response containing the analysis or description of
                the freshly captured photo.
        """
        self.capture_photo()

        self.model = ChatOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model_name,
            verbose=False,
            max_tokens = 256,
            max_retries = 3,
            timeout= 30
        )

        message = [HumanMessage(content=[
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "base64": self.encode_image_base64("generated/user.jpg"),
                "mime_type": "image/jpeg",
            }
        ]),
        SystemMessage("You are an Image expert. Describe each image according to the user's query and give very short answers.")
        ]

        analysis = str(self.model.invoke(message).content)

        return analysis