"""Select only the exact candidate named by the review workflow dispatch."""
import argparse,hashlib,json,re
from pathlib import Path
import runner_checkpoint,worker


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--sha256',required=True);args=p.parse_args()
    if not re.fullmatch('[a-f0-9]{64}',args.sha256):raise worker.AcquisitionError('INVALID_REVIEW_TARGET')
    root=runner_checkpoint.private_directory(args.state);queue=runner_checkpoint.queue(root,'official_close')
    jobs=[worker.unpacked(path.name[:64],queue.read(path),max_batch=8*1024*1024) for path in queue.entries()]
    if len(jobs)!=1 or not isinstance(jobs[0].get('document'),str) or hashlib.sha256(jobs[0]['document'].encode()).hexdigest()!=args.sha256:
        raise worker.AcquisitionError('OFFICIAL_REVIEW_TARGET_DIFFERS')
    print(json.dumps({'status':'EXACT_REVIEW_TARGET'}))


if __name__=='__main__':main()
