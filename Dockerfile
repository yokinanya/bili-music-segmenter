FROM tensorflow/tensorflow:2.18.0
RUN apt-get update && apt-get -y install ffmpeg wget git nodejs
WORKDIR /inaseg
COPY ./requirements.txt /inaseg/requirements.txt
RUN pip3 install -r /inaseg/requirements.txt
RUN wget https://getsamplefiles.com/download/mp3/sample-1.mp3 -P /home
COPY . /inaseg
# Testing
RUN python3 /inaseg/inaseg.py --media /home/sample-1.mp3
