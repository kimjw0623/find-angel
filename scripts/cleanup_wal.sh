#!/bin/bash

# SQLite WAL 파일 정리 스크립트
# WAL (Write-Ahead Logging) 체크포인트를 강제 실행하여 -wal과 -shm 파일을 정리합니다.

echo "=== SQLite WAL Checkpoint Script ==="
echo "This script will clean up SQLite WAL and SHM files"
echo ""

# Python 스크립트 실행
python3 << 'EOF'
import sqlite3
import os
from datetime import datetime

# 데이터베이스 파일 목록
db_files = ['lostark_auction.db', 'lostark_pattern.db']

print(f"Starting WAL cleanup at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("-" * 50)

for db_file in db_files:
    if os.path.exists(db_file):
        try:
            # 파일 크기 확인
            db_size = os.path.getsize(db_file) / 1024 / 1024  # MB
            wal_file = f"{db_file}-wal"
            shm_file = f"{db_file}-shm"
            
            wal_exists = os.path.exists(wal_file)
            shm_exists = os.path.exists(shm_file)
            
            print(f"\n📁 {db_file} ({db_size:.1f} MB)")
            
            if wal_exists:
                wal_size = os.path.getsize(wal_file) / 1024 / 1024  # MB
                print(f"  - WAL file: {wal_size:.1f} MB")
            else:
                print(f"  - WAL file: Not found")
                
            if shm_exists:
                shm_size = os.path.getsize(shm_file) / 1024  # KB
                print(f"  - SHM file: {shm_size:.1f} KB")
            else:
                print(f"  - SHM file: Not found")
            
            # WAL 체크포인트 실행
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # TRUNCATE 모드로 체크포인트 실행
            result = cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            
            # 결과: (busy, log_frames, checkpointed_frames)
            if result:
                busy, log_frames, checkpointed_frames = result
                if busy == 0:
                    print(f"  ✅ Checkpoint successful: {checkpointed_frames} frames checkpointed")
                else:
                    print(f"  ⚠️  Database is busy, partial checkpoint: {checkpointed_frames}/{log_frames} frames")
            
            conn.close()
            
            # 정리 후 상태 확인
            if os.path.exists(wal_file):
                print(f"  ⚠️  WAL file still exists (may be in use)")
            else:
                print(f"  ✅ WAL file removed")
                
            if os.path.exists(shm_file):
                print(f"  ⚠️  SHM file still exists (may be in use)")
            else:
                print(f"  ✅ SHM file removed")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    else:
        print(f"\n❌ {db_file} not found")

print("\n" + "-" * 50)
print("WAL cleanup completed")
EOF