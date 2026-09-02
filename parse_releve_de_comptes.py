import pandas as pd
from os import walk
from src.data_2025 import data_202512

invoices_folder = 'C:\\Users\\P5073668\\Documents\\Comptable\\Factures 2025'
filenames = next(walk(invoices_folder), (None, None, []))[2]  # [] if no file

#operations keywords
credit_operations = ["XINXUAN","ROLLAND MAXIME","BOUSQUET-CARTON","ARANIBAR","MOHAMMED","LAVILLE","VANZIELEGHEM", "BOUSQUET","JINGYI", "ROLLAND MAXIME", "PERION","FAURE", "MADINA","SERY","KOUADIO GOGOUA", "KRISHNADEV PAINIVEETIL", "NERI CATERINA", "TOURE", "QUATRAIN LILIA", "BARNICH - TALBOT"]
echeance_operations = ["ECH PRET"]
frais_operations = ["TENUE DE COMPTE"]
pret_copro_operations = ["ILE DE FRANCE"]
perso_operations = ["APPRO CC", "COMPLEMENT SALAIRE","AVANCE CC"]
water_operations = ["SUEZ EAU FRANCE SAS"]
insurance_operations = ["ASSURANCE DU PROPRIETAIRE NON"]
orange_operations = ["ORANGE SA"]
totalenergies_operations = ["TOTALENERGIES ELECTRI"]
airbnb_operations = ["AIRBNB"]
impots_operations = ["FINANCES PUBLIQUES"]
compta_operations = ["DELEHAYE"]

vals_locataires = ["XINXUAN","JINGYI","FAURE", "KOUADIO GOGOUA", "KRISHNADEV PAINIVEETIL","TOURE","SERY", "BOUSQUET-CARTON","VANZIELEGHEM","MOHAMMED","DANTONG"]
anzin_locataires = ["LILIA","ROLLAND MAXIME", "NERI CATERINA", "QUATRAIN LILIA", "BARNICH - TALBOT", "PERION", "MADINA", "LAVILLE","ARANIBAR"]

vals_operations = ["BV6550726", "VALS", "VALENCIENNES", "XXXX267", "DELEHAYE"]
anzin_operations = ["BV6539092", "ANZIN","KRISHNA", "XXXX730"]

lines_consolidated_descriptions = []
lines_consolidated = []

#combine all months data
data = ''.join([data_202512]).replace('\n\n','\n').strip()

lines = data.split('\n')

for line in lines:
    parts = line.split()
    if parts[0].count('/') == 2:
        if len(parts) >= 4:
            date = parts[1]
            description = ' '.join(parts[2:-1])
            amount = parts[-1]
            lines_consolidated_descriptions.append((date, description, amount))
            #print(f"Date: {date}, Description: {description}, Amount: {amount}")
    else:
        if lines_consolidated_descriptions:
            last_entry = lines_consolidated_descriptions[-1]
            new_description = last_entry[1] + ' ' + ' '.join(parts)
            lines_consolidated_descriptions[-1] = (last_entry[0], new_description, last_entry[2])
        else:
            print("Warning: Found continuation line without a preceding entry.")

print("\nConsolidated Entries:")
for entry in lines_consolidated_descriptions:
    
    #set place based on description content
    is_anzin = any(anzin_op in entry[1] for anzin_op in anzin_locataires)
    is_vals = any(vals_op in entry[1] for vals_op in vals_locataires)

    #set motif based on description content
    is_quittance = any(credit_op in entry[1] for credit_op in credit_operations)
    is_echeance = any(echeance_op in entry[1] for echeance_op in echeance_operations)
    is_frais = any(frais_op in entry[1] for frais_op in frais_operations)
    is_pret_copro = any(pret_op in entry[1] for pret_op in pret_copro_operations)
    is_perso = any(perso_op in entry[1] for perso_op in perso_operations)
    is_water = any(water_op in entry[1] for water_op in water_operations)
    is_insurance_operations = any(insurance_op in entry[1] for insurance_op in insurance_operations)
    is_orange = any(orange_op in entry[1] for orange_op in orange_operations)
    is_totalenergies = any(total_op in entry[1] for total_op in totalenergies_operations)
    is_airbnb = any(airbnb_op in entry[1] for airbnb_op in airbnb_operations)
    is_impots = any(impots_op in entry[1] for impots_op in impots_operations)
    is_compta = any(compta_op in entry[1] for compta_op in compta_operations)
    is_anzin = is_anzin or (any(op in entry[1] for op in anzin_operations))
    is_vals = is_vals or (any(op in entry[1] for op in vals_operations))

    motif = "quittance de loyer" if is_quittance else "echéance de prêt" if is_echeance else "frais de tenue de compte" if is_frais else "prêt copropriété" if is_pret_copro else "virement personnel" if is_perso else "provision consommation eau" if is_water else "assurance PNO" if is_insurance_operations else "abonnement internet" if is_orange else "consommation électricité" if is_totalenergies else "location airbnb" if is_airbnb else "impôts" if is_impots else "gestion comptabilité" if is_compta else ""
   
    try:
        amount = (float(entry[2].replace(',','.')))
    except ValueError:
        amount = (float(entry[2].replace('.','').replace(',','.')))
    
    day = int(entry[0][:2])

    is_vals = ((int(amount) >= 890 and int(amount) < 900) and is_echeance) or is_vals
    is_vals = (int(amount) > 70 and is_water) or is_vals
    is_vals = (day >= 12 and day <= 17) and is_totalenergies or is_vals

    is_anzin = ((int(amount) >= 540 and int(amount) < 550) and is_echeance) or is_anzin or is_frais
    is_anzin = (int(amount) < 70 and is_water) or is_anzin
    is_anzin = (day >= 23 and day <= 27) and is_totalenergies or is_anzin
    is_lille = not is_anzin and not is_vals and is_pret_copro
    
    is_perso = not is_anzin and not is_vals and is_perso

    place = "Anzin" if is_anzin else "Vals" if is_vals else "Lille" if is_lille else "Perso" if is_perso else ""
    amount = f"{amount:.2f}"

    #find corresponding invoice file
    invoice_file = ""
    
    for filename in filenames:
        try:
            price, cents, currency = filename.split('.')[0].split('_')[-3:]
        except ValueError:
            continue
        if price.isnumeric() and cents.isnumeric() and currency == 'eur':
            price_cents_cur = f"{price}_{cents}_{currency}"
            if f"{amount.replace('.','_')}_eur" in price_cents_cur:
                invoice_file = filename
                break

    if any(credit_op in entry[1] for credit_op in credit_operations):
        lines_consolidated.append([place, entry[0], entry[1], '',amount,motif, invoice_file])
    else:
        lines_consolidated.append([place, entry[0], entry[1],amount,'',motif, invoice_file])

for line in lines_consolidated:
    print(line) 

#create dataframe and save to excel
df = pd.DataFrame(lines_consolidated, columns=['Place', 'Date', 'Description', 'Debit', 'Credit', 'Motif','Fichier'])
df.to_excel('out/releve_de_comptes_parsed.xlsx', index=False)

print("\nDataFrame saved to 'out/releve_de_comptes_parsed.xlsx'")