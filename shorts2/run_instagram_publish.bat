@echo off
cd /d "C:\Users\LG\Desktop\blog_auto\claude\shorts2"
python instagram_publish.py "https://drive.usercontent.google.com/download?id=1pYBfqHlzyR1Ki7xaKXFsEkq5HDqHeho3^&export=download" caption.txt >> publish_log.txt 2>&1
