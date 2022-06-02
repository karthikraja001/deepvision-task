import datetime
from unicodedata import name
from bson import ObjectId
from flask import Flask,request,render_template,redirect, session, abort, url_for
import os
import moviepy.editor as mp
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
from google.oauth2 import id_token
import pymongo
import requests
import time
import azure.cognitiveservices.speech as speechsdk
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from dotenv import load_dotenv
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,RT'

load_dotenv()
AZURE_KEY = os.getenv('KEY1')
print(AZURE_KEY)

client = pymongo.MongoClient("mongodb+srv://vignesh01:vignesh01@transcriptions.zva3p.mongodb.net/?retryWrites=true&w=majority")
db = client.get_database('transcriptions')

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app.config["VIDEO_UPLOADS"] = "static\Videos"
flow = Flow.from_client_secrets_file(
    client_secrets_file='client_secret.json',
    scopes=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    redirect_uri='http://localhost:2000/oauth2callback'
)

# def speech_to_text(audioPath):
#     """performs one-shot speech recognition with input from an audio file"""
#     speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, endpoint='https://southeastasia.api.cognitive.microsoft.com/sts/v1.0/issuetoken')
#     audio_config = speechsdk.audio.AudioConfig(filename=audioPath)
#     speech_recognizer = speechsdk.SpeechRecognizer(
#         speech_config=speech_config, language="en-US", audio_config=audio_config)

#     result = speech_recognizer.recognize_once()
#     if result.reason == speechsdk.ResultReason.RecognizedSpeech:
#         return ("Recognized: {}".format(result.text))
#     elif result.reason == speechsdk.ResultReason.NoMatch:
#         return ("No speech could be recognized: {}".format(result.no_match_details))
#     elif result.reason == speechsdk.ResultReason.Canceled:
#         cancellation_details = result.cancellation_details
#         return ("Speech Recognition canceled: {}".format(cancellation_details.reason))

# def speech_recognize_async_from_file(audiopath):
#     """performs one-shot speech recognition asynchronously with input from an audio file"""
#     speech_config = speechsdk.SpeechConfig(subscription='AZURE_KEY', region='southeastasia')
#     audio_config = speechsdk.audio.AudioConfig(filename=audiopath)
#     speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
#     result_future = speech_recognizer.recognize_once_async()

#     print('recognition is running....')
#     result = result_future.get()

#     if result.reason == speechsdk.ResultReason.RecognizedSpeech:
#         print("Recognized: {}".format(result.text))
#     elif result.reason == speechsdk.ResultReason.NoMatch:
#         print("No speech could be recognized: {}".format(result.no_match_details))
#     elif result.reason == speechsdk.ResultReason.Canceled:
#         cancellation_details = result.cancellation_details
#         print("Speech Recognition canceled: {}".format(cancellation_details.reason))
#         if cancellation_details.reason == speechsdk.CancellationReason.Error:
#             print("Error details: {}".format(cancellation_details.error_details))

def speech_recognize_continuous_from_file(audiopath, audioName):
    """performs continuous speech recognition with input from an audio file"""
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region='southeastasia')
    audio_config = speechsdk.audio.AudioConfig(filename=audiopath)

    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    done = False

    def stop_cb(evt):
        """callback that stops continuous recognition upon receiving an event `evt`"""
        print('CLOSING on {}'.format(evt))
        speech_recognizer.stop_continuous_recognition()
        nonlocal done
        done = True

    all_results = []

    def handle_final_result(evt):
        all_results.append(evt.result.text)
        speech_recognizer.recognized.connect(handle_final_result)

    speech_recognizer.recognizing.connect(lambda evt: print('RECOGNIZING: {}'.format(evt)))
    speech_recognizer.recognized.connect(handle_final_result)
    speech_recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
    speech_recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
    speech_recognizer.canceled.connect(lambda evt: print('CANCELED {}'.format(evt)))
    speech_recognizer.session_stopped.connect(stop_cb)
    speech_recognizer.canceled.connect(stop_cb)

    speech_recognizer.start_continuous_recognition()
    while not done:
        time.sleep(.5)
    print(all_results)
    finalString = " ".join(all_results)
    if len(finalString) != 0:
        db.transcription.insert_one({'transcription': finalString, 'filename': audioName, 'uid': session['google_id'], 'timestamp': datetime.datetime.now()})
    elif 'No speech'.lower() in finalString.lower():
        finalString = '!!!No Speech Detected in this video!!!'
    elif len(finalString) == 0:
        finalString = '!!!No Speech Detected in this video!!!'
    else:
        finalString = finalString
        db.transcription.insert_one({'transcription': finalString, 'filename': audioName, 'uid': session['google_id'], 'timestamp': datetime.datetime.now()})

    return finalString


def loginRequired(function):
    def wrapper(*args,**kwargs):
        print(session)
        if 'name' in session:
            return function()
        else:
            return redirect('/login')
    return wrapper

def loginForTranscribe(function):
    def wrapperTranscribe(*args,**kwargs):
        if 'name' in session:
            return function()
        else:
            return redirect('/login')
    return wrapperTranscribe

def loginForDelete(function):
    def wrapperDelete(*args,**kwargs):
        if 'name' in session:
            return function()
        else:
            return redirect('/login')
    return wrapperDelete

@app.route('/home',methods = ["GET","POST"])
@loginRequired
def upload_video():
    if request.method == "POST":
        video = request.files['file']

        if(request.form['videoName']):
            name = request.form['videoName']
        else:
            name = secure_filename(video.filename)
            print('name:\t\t',name)

        if video.filename == '':
            print("Video must have a file name")
            return render_template("main.html",filename='',resultFound='No file uploaded. Please upload a file for transcription',userName=session['name'])
    
        filename = "video.mp4"

        basedir = os.path.abspath(os.path.dirname(__file__))
        video.save(os.path.join(basedir,app.config["VIDEO_UPLOADS"],filename))
        clip = mp.VideoFileClip(os.path.join(basedir,app.config["VIDEO_UPLOADS"],filename))
        clip.audio.write_audiofile(os.path.join(basedir,app.config["VIDEO_UPLOADS"],"audio.wav"))
        result = speech_recognize_continuous_from_file(os.path.join(basedir,app.config["VIDEO_UPLOADS"],"audio.wav"), name)
        print("Result is:",result)
        # db.transcription.insert_one({"name":name,"transcription":result,"video":filename,'timestamp':datetime.datetime.now(),'uid':session['google_id']})
        
        return render_template("main.html",filename=name,resultFound=result,userName=session['name'])

    return render_template('main.html',userName=session['name'])

    # return render_template('main.html',userName=session['name'])
    
@app.route('/history',methods = ["GET","POST"])
@loginForTranscribe
def history():
    resultset = db.get_collection('transcription').find({'uid':session['google_id']})
    x = (list(resultset))
    for i in x:
        i['timestamp'] = i['timestamp'].strftime("%d-%m-%Y %H:%M:%S")
    x = sorted(x, key=lambda i: i['timestamp'], reverse=True)
    # print(x[0]['_id'])
    return render_template('history.html',resultset=x, theSample = '<div class="card"><h4><b>file name</b></h4><p>date and time</p></div>', userName=session['name'])

# @app.route('/delete/<int:transcription_id>',methods = ["GET","POST"])
# @loginForDelete
# def delete_transcription(id):
#     if request.method == "POST":
#         db.get_collection('transcription').delete_one({'_id':ObjectId(id)})
#     return redirect(url_for('history'))

@app.route('/delete', methods=['POST'])
@loginForDelete
def delete_movie():
    if request.method == 'POST':
        print("request", request.form)
        db.get_collection('transcription').delete_one({'_id':ObjectId(request.form.get('theId'))})
    return redirect('/history')

@app.route('/oauth2callback', methods=['GET', 'POST'])
def callback():
    flow.fetch_token(authorization_response=request.url)    
    credentials = flow.credentials
    request_session = requests.Session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)
    id_info = id_token.verify_oauth2_token(id_token=credentials.id_token, request=token_request)

    record = db.get_collection('users').find_one({'uid':id_info['sub']})
    if not record:
        db.get_collection('users').insert_one({'uid':id_info['sub'],'name':id_info['name'],'email':id_info['email']})
    else:
        session['name'] = id_info['name']
        session['google_id'] = id_info.get("sub")
        session['name'] = id_info.get("name")
    return redirect('/home')

# @app.route('/transcribe',methods=['GET','POST'])
# def transcribe():
#     if request.method == 'POST':
#         if 'video' not in request.files:
#             return redirect(request.url)
#         video = request.files['video']
#         if video.filename == '':
#             return redirect(request.url)
#     return render_template("transcribe.html", userName=session['name'])

@app.route('/login',methods=['GET','POST'])
def loginPage():
    auth_url, state = flow.authorization_url()
    session['oauth_state'] = state
    return redirect(auth_url)

@app.route('/',methods=['GET','POST'])
def index():
    return render_template("home.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

app.run(debug=True,port=2000)