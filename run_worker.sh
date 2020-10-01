set -e
eval $NFSMNT

python3 -m celery -A demo_project worker -l debug --concurrency=4 &

aria2c --enable-rpc --rpc-listen-all=true --rpc-allow-origin-all -c
