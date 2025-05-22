import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import os
import re # Make sure re is imported if you're using it in candidate_tags for cleaning

class ImageTagger:
    def __init__(self, custom_tags=None):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
        self.model.eval()
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # Define candidate tags with full sentences/descriptive phrases
        self.base_candidate_tags = [
            "a photo of sky"
            
        ]

        all_tags = self.base_candidate_tags + (custom_tags if custom_tags is not None else [])
        self.candidate_tags = sorted(list(set(all_tags)))

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

            # Store the raw tag (e.g., "a photo of a landscape")
            # The cleaning (removing "a photo of a ") should happen when constructing the filename
            top_tags_with_probs = [
                (self.candidate_tags[idx], image_probs[idx])
                for idx in top_indices
            ]

            results[original_path] = top_tags_with_probs
        
        return results
    
    # for a single image (kept for consistency, but batch is preferred for efficiency)
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