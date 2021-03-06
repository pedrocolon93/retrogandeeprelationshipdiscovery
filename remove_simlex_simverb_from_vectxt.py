def clean_constraints(filename,slsv_words):
    ants = []
    with open(filename) as f:
        for antonym in f:
            w1, w2 = antonym.split(" ")
            if w1.strip() in slsv_words or w2.strip() in slsv_words:
                continue
            else:
                ants.append(antonym)
    return ants

if __name__ == "__main__":
    slsv_words = ""
    simlexverb_text_file = "simlexsimverb_words.txt"
    with open(simlexverb_text_file) as f:
        for line in f:
            slsv_words+=line+"\n"

    ants = clean_constraints("/media/pedro/ssd_ext/LEAR/linguistic_constraints/antonyms.txt",slsv_words)
    with open("clean_ant","w") as f:
        f.writelines(ants)   
    syns = clean_constraints("/media/pedro/ssd_ext/LEAR/linguistic_constraints/synonyms.txt",slsv_words)
    with open("clean_syn.txt","w") as f:
        f.writelines(syns)       
