import csv, json

csvFilePath = ""
jsonFilePath = ""

data = {}
with open(csvFilePath) as csvFile:
    csvReader = csv.DictReader(csvFile)
    for row in csvReader:
        for key in row:
            try:
                row[key] = eval(row[key])
            except:
                pass
        data = row

with open(jsonFilePath, 'w') as jsonFile:
    jsonFile.write(json.dumps(data, indent=4))
