import os
files = os.listdir('Artifacts')
for f in files:
    print(f.encode('utf-8', 'ignore').decode('utf-8'))
