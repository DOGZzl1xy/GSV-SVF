# Source code from https://github.com/koito19960406/ZenSVI

import subprocess
import os
""" result = subprocess.run('bash -c "source /etc/network_turbo && env | grep proxy"', shell=True, capture_output=True, text=True)
output = result.stdout
for line in output.splitlines():
    if '=' in line:
        var, value = line.split('=', 1)
        os.environ[var] = value """
from zensvi.cv import Segmenter


# model weights is groundingdino_swint_ogc.pth if you are in China, please put it into the same directory as this script
# please check if your image is directly in folder, or in a subfolder. 
# For me, path will be 'GoogleStreetViews/SF_2023/SF', where photos are in SF folder.
input_directory = os.path.abspath("GoogleStreetViews/YOUR_OWN_CITY_NAME_year/")             #replace with your own path, like SF_2023
output_directory = os.path.abspath("GoogleStreetViews/YOUR_OWN_CITY_NAME_year/Seg")         #replace with your own path, like SF_2023/Seg
summary_directory = os.path.abspath("GoogleStreetViews/YOUR_OWN_CITY_NAME_year/summary")    #replace with your own path, like SF_2023/summary

# Create output directories if they don't exist
os.makedirs(output_directory, exist_ok=True)
os.makedirs(summary_directory, exist_ok=True)

segmenter = Segmenter(
    dataset="cityscapes",  
    task="semantic"        
)

print(f"Starting segmentation of images from {input_directory}...")
segmenter.segment(
    input_directory,                
    dir_image_output=output_directory,     
    dir_summary_output=summary_directory   
)
print(f"Segmentation completed. Results saved to {output_directory}")