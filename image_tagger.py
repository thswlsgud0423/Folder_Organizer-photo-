import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import os

class ImageTagger:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load model and processor
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
        self.model.eval()
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # Define candidate tags # written by NLP model no way i write this 
        self.candidate_tags = [
            # --- Photographic Styles & Genres ---
            "landscape",
            "portrait",
            "street photography",
            "documentary",
            "travel photography",
            "macro",
            "architectural",
            "wildlife",
            "sports photography",
            "event photography",
            "fine art photography",
            "still life",
            "food photography",
            "product photography",
            "astrophotography",
            "underwater photography",
            "aerial photography",
            "fashion photography",
            "urban exploration",
            "concert photography",

            # --- Composition & Framing ---
            "wide angle",
            "close-up",
            "full shot",
            "panoramic",
            "background blur",


            # --- Lighting & Atmosphere ---
            "natural light",
            "artificial light",
            "studio light",
            "flash photography",
            "soft light",
            "hard light",
            "low light",
            "sunrise",
            "sunset",
            "daylight",
            "nighttime",
            "sunny",
            "cloudy",
            "fog",
            "mist",
            "haze",
            "rain",
            "snow",

            # --- Colors & Tones ---
            "black and white",
            "monochromatic",
            "vibrant colors",
            "muted colors",
            "pastel colors",
            "warm tones",
            "cool tones",
            "high contrast",
            "low contrast",
            "bright",
            "dark",
            "colorful",
            "desaturated",
            "HDR", # High Dynamic Range

            # --- Subjects - People & Life ---
            "person",
            "people",
            "child",
            "baby",
            "family",
            "couple",
            "friends",
            "self-portrait",
            "male portrait",
            "female portrait",
            "street performer",
            "crowd",
            "people walking",
            "people interacting",
            "smiling",
            "laughing",
            "action shot",
            "emotion",
            "happiness",
            "sadness",
            "contemplation",

            # --- Subjects - Animals & Wildlife ---
            "dog",
            "cat",
            "bird",
            "wildlife",
            "animal portrait",
            "animal in nature",
            "insect",
            "mammal",
            "reptile",
            "fish",
            "pet photography",
            "feathered",
            "furry",
            "scales",

            # --- Subjects - Nature & Landscapes ---
            "mountains",
            "forest",
            "trees",
            "flowers",
            "garden",
            "field",
            "grasslands",
            "beach",
            "ocean",
            "lake",
            "river",
            "waterfall",
            "desert",
            "sand dunes",
            "rocks",
            "path",
            "trail",
            "sky",
            "clouds",
            "stars",
            "moon",
            "sun",
            "autumn leaves",
            "spring blossoms",
            "cave",
            "valley",
            "canyon",
            "coastline",
            "waves",
            "plant",
            "fungi",
            "ice",
            "glacier",
            "volcano",
            "island",
            "rural landscape",
            "countryside",

            # --- Subjects - Urban & Architecture ---
            "cityscape",
            "urban scene",
            "buildings",
            "street",
            "road",
            "alleyway",
            "bridge",
            "architecture",
            "historical building",
            "modern building",
            "landmark",
            "monument",
            "statue",
            "house",
            "structure",
            "facade",
            "window",
            "door",
            "street art",
            "graffiti",
            "night city lights",
            "public square",
            "market",
            "temple",
            "church",
            "castle",
            "factory",
            "industrial area",
            "pier",
            "harbor",
            "skyline",
            "traffic",
            "neon lights",
            "subway",


            # --- Mood & Aesthetic ---
            "peaceful",
            "calm",
            "dramatic",
            "moody",
            "joyful",
            "happy",
            "energetic",
            "emotional",
            "beautiful",
            "modern",
            "vintage",
            "love",
        ]

        self.text_inputs = self.processor(
            text=self.candidate_tags,
            return_tensors="pt",
            padding=True,
            truncation=True
        ).to(self.device)

    def tag_images_batch(self, image_paths, num_top_tags=5):
        """
        Tags a batch of images and returns a dictionary of {image_path: [(tag, probability), ...]}.
        """
        if not image_paths:
            return {}

        images = []
        original_paths = []

        for img_path in image_paths:
            try:
                # Open each image file
                img = Image.open(img_path).convert("RGB")
                images.append(img)
                original_paths.append(img_path) # Keep track of its original path
            except Exception:
                continue

        if not images:
            return {}
        # Preprocess Images with CLIP Processor
        # 'return_tensors="pt"' ensures the output is PyTorch tensors.
        image_inputs = self.processor(images=images, return_tensors="pt", padding=True)
        pixel_values = image_inputs.pixel_values.to(self.device)

        # perform CLIP Model
        with torch.no_grad():
            outputs = self.model(pixel_values=pixel_values, **self.text_inputs)

        # 'outputs.logits_per_image' contains the raw similarity scores between each image and each text tag
        logits_per_image = outputs.logits_per_image

        # Apply softmax to convert raw similarity scores into probabilities
        probs = logits_per_image.softmax(dim=1).cpu().numpy()

        # extract Top Tags
        results = {}
        for i, original_path in enumerate(original_paths):
            image_probs = probs[i]
            top_indices = image_probs.argsort()[-num_top_tags:][::-1]

            top_tags_with_probs = [
                (self.candidate_tags[idx], image_probs[idx])
                for idx in top_indices
            ]

            results[original_path] = top_tags_with_probs
    
        return results
    
    # for a single image
    def tag_image(self, image_path, num_top_tags=5):
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            return []

        image_inputs = self.processor(images=image, return_tensors="pt", padding=True)
        pixel_values = image_inputs.pixel_values.to(self.device)

        with torch.no_grad():
            outputs = self.model(pixel_values=pixel_values, **self.text_inputs)

        logits_per_image = outputs.logits_per_image

        probs = logits_per_image.softmax(dim=1)
        top_indices = probs.argsort(dim=-1, descending=True)[0, :num_top_tags]
        
        top_tags_with_probs = [
            (self.candidate_tags[idx], probs[0, idx].item())
            for idx in top_indices
        ]
        
        return top_tags_with_probs
    