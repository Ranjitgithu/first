import os
import zipfile

def create_zip_file(file_paths, output_path):
    
    try:
        with zipfile.ZipFile(output_path, 'w') as zipf:
            for file_path in file_paths:
                # Get just the filename without the path
                file_name = os.path.basename(file_path)
                # Add file to ZIP with the original filename
                zipf.write(file_path, arcname=file_name)
    except Exception as e:
        raise Exception(f"Error creating ZIP file: {str(e)}")