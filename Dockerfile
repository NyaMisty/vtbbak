FROM ubuntu:18.04

ENV NFSMNT ""

WORKDIR /app

RUN apt update && apt install -y nfs-common aria2 python3 python3-pip && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

COPY . /app/
#RUN cd /tmp && git clone https://github.com/NyaMisty/vtbbak

CMD ['./run_workers.sh']