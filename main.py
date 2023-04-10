from flask import Flask, render_template, jsonify, request
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from werkzeug.utils import secure_filename
import os
from wtforms.validators import InputRequired

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/files'

class UploadFileForm(FlaskForm):
    file = FileField("File", validators=[InputRequired()])
    submit = SubmitField("Upload File")

@app.route('/', methods=['GET',"POST"])
@app.route('/home', methods=['GET',"POST"])
def home():
    form = UploadFileForm()
    if form.validate_on_submit():
        file = form.file.data # First grab the file
        file.save(os.path.join(os.path.abspath(os.path.dirname(__file__)),app.config['UPLOAD_FOLDER'],secure_filename(file.filename))) # Then save the file
        return "File has been uploaded."
    return render_template('index.html', form=form)

@app.route('/get-keys', methods=['POST'])
def get_keys():
    json_data = request.get_json()
    
    keys = list(json_data.keys())
    return jsonify(keys)

# @app.route(
#     '/pdf2tiff', methods=['POST'], endpoint='convert_pdf_to_images')
# @validate_jwt
# def convert_pdf_to_images():

#     if request.method == 'POST':
#         try: 
#             data = request.get_data()
#         except:
#             print("Unexpected error :", sys.exc_info()[0])
#             raise

#         try: 
#             images = convert_from_bytes(
#                 data,
#                 dpi=200)
#         except:
#             print("Unexpected error :", sys.exc_info()[0])
#             raise

#         msecpart=datetime.datetime.now().strftime("%f")
#         dir_path = os.path.dirname(os.path.realpath(__file__))
#         output_folder = dir_path+f"/data-{randint(0,1000000000)}-{msecpart}"

#         try:
#             os.makedirs(output_folder)
#             print(f"directory {output_folder} created successfully")
#         except:
#             print("Unexpected error :", sys.exc_info()[0])
#             raise

#         for index, image in enumerate(images):
#             try:
#                 image.save(f'{output_folder}/image-converted-from-bytes{index}.tiff')
#             except:
#                 print("Unexpected error :", sys.exc_info()[0])
#                 raise

            

#         #Read all tiff images and base64 encode
#         tif_images = os.listdir(output_folder)
#         print(f"tif images saved {tif_images}")

#         encoded_images = {}
#         for index, tif_image in enumerate(tif_images):
#             tif_image_full_path = f'{output_folder}/{tif_image}'
            
#             print(f"tif image full path {tif_image_full_path}")
            
#             with open(tif_image_full_path, "rb") as f:
#                 tif_file = base64.b64encode(f.read())
#                 tif_file_str = tif_file.decode("utf-8")

#             try:
#                 encoded_images[index] = tif_file_str
#             except:
#                 print(
#                     "Unexpected error with creating obj to be returned:",
#                     sys.exc_info()[0])
#                 raise

#         # Deletes all saved images and returns a binary of TIFF images
#         for tif_image in tif_images:
#             tif_image_full_path = f'{output_folder}/{tif_image}'
#             os.remove(tif_image_full_path) 
        
#         try:
#             os.rmdir(output_folder)
#             print(f"directory {output_folder} removed successfully")
#         except:
#             print("Unexpected error:", sys.exc_info()[0])
#             print(f"failed to remove the directory {output_folder}")

#         return jsonify(encoded_images)

if __name__ == '__main__':
    app.run(debug=True)