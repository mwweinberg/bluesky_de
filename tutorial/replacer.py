import re 



input_string = "Next Wednesday, the collective bargaining negotiations between the #Berliner Verkehrsbetriebe and -h-Verdi will start. The union is demanding 750 euros more per month - if the #BVG does not meet the Verdi union&#39;s demands, the latter is threatening #strikes"


#rep = str.maketrans({"-h-": "#", "&#39;": "'"})


new_string = (
    input_string
        .replace("-h-","#")
        .replace("&#39;", "'")
)

print(new_string)


