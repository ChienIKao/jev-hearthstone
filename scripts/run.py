"""Launch one application role from a source checkout."""
import argparse
from pathlib import Path
import runpy
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('role',choices=['android_app','app','reader','advisor'])
    args=parser.parse_args(sys.argv[1:2])
    remaining=sys.argv[2:]
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
    sys.argv=[args.role]+remaining
    runpy.run_module('laya_hearthstone.'+args.role,run_name='__main__')


if __name__=='__main__':main()
