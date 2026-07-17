#!/usr/bin/env python3
"""Generate data/staff_source_permanent.xlsx and data/staff_source_dsa.xlsx from the
staff lists Josh supplied. Transcribed verbatim from the supplied tables — SPOT-CHECK
before relying on it. Run from repo root, then run ingest_staff.py.

    python make_staff_sources.py
"""
import os, sys

PERM = """70|Pauline Wairimu Omondi|Senior Reconciliations Officer|Internal Control
96|Joyce Nyambura Mwangi|Customer Service Manager|Commercial Banking
101|Isabella Mbula Manthi|Cheque Validation Officer|Operations & Technology
150|Martha Muthoni Muraya|Branch Manager|Commercial Banking
175|Peninah Wanjiru Njenga|Senior FX Trader|Treasury
176|Geoffrey Nderitu Muthui|Head Information & Techonolgy|Operations & Technology
177|Moses Migwi Karimi|Senior Service Officer, Technology (Applications)|Operations & Technology
232|Ayub Maina|Service Officer- Payments|Operations & Technology
284|George Pino|Manager Operation Risk|Risk
292|Tabman Odhiambo Nyaoro|Senior Service Officer, Technology (Networks & Telcoms)|Operations & Technology
305|David Kimani Kinyanjui|Service Officer, TROPS|Operations & Technology
313|Philgona Akinyi Odera|Branch Operations Officer|Commercial Banking
314|Phyllis Sibolo|Team Leader, Trade & Trops|Operations & Technology
317|Christine Achieng Kiche|Acting HR Head|Human Resources
322|Thaddaeus Mboga Okwaro|Zonal Manager & Branch Manager|Commercial Banking
332|Ruth Wambui Thairu|Branch Manager|Commercial Banking
343|Nancy Akoth Oywer|Relationship Officer|Consumer Banking
345|Josephine Gakii Gituma|Customer Service Manager|Commercial Banking
356|Hellen Wangui Gathii|Branch Manager|Commercial Banking
357|Judy Njeri Irungu|Finanacial Risk Manager|Risk Management
395|Violet Bochere Monari|Zonal Manager & Branch Manager|Commercial Banking
397|Charles Maunda Orina|Chauffeur|Operations & Technology
399|Abdalla Mohamed Ali|Product Manager|Operations & Technology
406|Benjamin Muthini|Finance Officer|Finance
408|Mary Chepkemboi Lagat|Customer Service Manager|Commercial Banking
412|Moses Bwogo Nyandiko|Chauffeur|Operations & Technology
439|Ludy Chebet Mining|Customer Service Manager|Commercial Banking
443|Caroline Mbenge Wambua|Director, Legal Services & Company Secretary|Legal
445|Jennifer Waithera Macharia|Relationship Officer|Consumer Banking
451|Nirmal Singh Sembi|Information Systems Auditor|Internal Audit
461|Betty Wachera Waiguru|Customer Service Manager|Commercial Banking
467|Caren Mbithe Nyakundi|Branch Operations Officer|Commercial Banking
484|Florence Wanjiru Mbuthia|Customer Service Manager|Commercial Banking
486|Stellah Cherop Maina|Operations Manager, Payments, RPC & Remittances|Operations & Technology
507|Rachel Watiri Muriithi|Payments Operations Officer|Operations & Technology
508|Nelly Mjomba|Branch Operations Officer|Commercial Banking
519|Margaret Wambui Wairimu|Customer Service Manager|Commercial Banking
526|Amina Adam|Customer Service Manager|Commercial Banking
539|Lucy Kamede Lidahuli|Relationship Manager, Premier Banking|Consumer Banking
545|Robert Oginda Siro|Manager, Financial Control & Regulatory Reporting|Finance
546|Elizabeth Nyawira Miano|Customer Service Manager|Commercial Banking
555|Mary Wangari Wanjiru|Chief Finance Officer|Finance
557|Christine Wahu Wanyoike|Operations Manager, Treasury & Trade Operations|Operations & Technology
561|Susan Akoth Abok|Branch Operations Officer|Commercial Banking
569|Paulina Anna Wangare|Compliance Officer|Compliance
573|Divinah Kwamboka Ondimu|Assistant Branch Operations & Service Manager|Commercial Banking
587|Evans Mwaura Ngugi|Internal Control Officer|Internal Control
592|Edward Muchoki Mbugua|Physical Security, Logistics & Transport|Operations & Technology
594|Rosemary Gaicugi Gitonga|Head of Cusomer Experience Kenya & CESA 1|Customer Experience
603|Alexander Maina Kibaara|Director, Internal Control|Internal Control
621|Trevor Omondi Otieno|Senior Officer, Payments & Digital Channels|Consumer Banking
632|Joyce Gituura Meeme|Branch Manager|Commercial Banking
637|Brenda Cherono Rono|Customer Service Manager|Commercial Banking
639|Nelly Ogutu|Client Engagement Manager, Corporate Banking|Corporate Banking
662|Faith Jemutai Koech|Assistant Branch Operations & Service Manager|Commercial Banking
668|Billy Calary Arika|Assistant Branch Operations & Service Manager|Commercial Banking
672|Martin Maina Muritu|Branch Operations Officer|Commercial Banking
677|Stephen Otieno Omondi|Head of Reconciliations & Balance Sheet Assurance|Internal Control
691|Edmund Uledi Moga|Operations Manager, Branch Operations & Retail Support|Operations & Technology
701|Enid Jesang Tallam|HR Services Manager|Human Resources
708|Maryanne Njeri Chege|Customer Service Manager|Commercial Banking
718|Rosabeth Theuri|Reconciliations Officer|Internal Control
723|Loryne Bulimo|Branch Operations Officer|Commercial Banking
741|Clare Wairimu Njeri|Service Assistant, Operations Officer|Operations & Technology
745|David Macharia Murigi|Manager, Operations Risk|Risk
748|Nicholus Macharia Karani|Internal Control Officer|Internal Control
754|Latifa Achieng Outa|Director, Internal Audit|Internal Audit
762|Caroline Nduta Gakinya|Branch Operations Officer|Commercial Banking
776|Eric Muchai Mwongera|Team Leader-Cards, Mobile and Digital Products|Operations & Technology
792|Esther Wangari Mathenge|Assistant Branch & Service Operations Manager|Commercial Banking
793|Mercy Mueni Inyama|Branch Operations Officer|Commercial Banking
801|Hilda Nyaboke Osoro|Assistant Branch Operations & Service Manager|Commercial Banking
807|Fenella Mwamburi|Assistant Branch Service & Operations Manager|Commercial Banking
810|Caroline Gateru|Branch Operations Officer|Commercial Banking
812|Barbara Robi Mwita|Operations Officer|Operations & Technology
814|Loise Wanjiru Ributhi|Customer Service Manager|Commercial Banking
816|Annette Wambui Kamere|Head, Consumer Products|Consumer Banking
820|Thomas Okumu|Director, Credit Risk Management- Kenya & EAC|Credit Risk Management
822|Vincent Kipkoech Langat|Branch Operations Officer|Commercial Banking
824|Patrick Muthui Katuta|Operations Assistant Officer|Operations & Technology
827|Veronica Lalarari|Relationship Manager, Premier Banking|Consumer Banking
831|Brenda Sawo|Quality Analyst|Customer Experience
833|Benson Oloo Omondi|Assistant Branch Service & Operations Manager|Commercial Banking
834|Salome Nganga|Operations Officer|Operations & Technology
840|Samuel Magothe|Relationship Manager, Regional Corporates|Corporate Banking
852|Faith Sungu Busolo|Assistant Branch Service & Operations Manager|Commercial Banking
859|Jackline Nyakerario Mainye|Customer Service Manager|Commercial Banking
867|Frankline Koriko Obuya|Head Informations Security & BCP|Risk
870|Naomi Muthoni Muriuki|Branch Operations Officer|Commercial Banking
874|Mercy Wanjiru Kabuiku|Operations Officer|Operations & Technology
886|Michelle Mwihaki Mwangi|Internal Control Officer|Internal Control
887|John Njogu Waithaka|Relationship Officer|Consumer Banking
894|Ruby Michelle Cherotich|Branch Operations Officer|Commercial Banking
899|Abdul Hafiz Otieno|Reconciliations Officer|Internal Control
902|Alfred Muriithi Maringa|Procurement & vendor Management Officer|Operations & Technology
905|Frida Alice Karimi Njiru|Senior Internal Auditor|Internal Audit
913|Judy Mwende Muthama|Branch Operations Officer|Commercial Banking
949|Monicah Nyambura Gikonyo|Relationship Officer|Consumer Banking
954|Fred Wanyonyi Mutekhele|Customer Insights & Analytics Manager|Customer Experience
955|Bertha Ngala Mulumia|Customer Service Manager|Commercial Banking
956|Sera Wanjiru Njuguna|Head, CAD|Credit Risk Management
958|Tamara Kageha Kidulla|Branch Operations Officer|Commercial Banking
959|Victor Mutabari Mbaabu|Head EFS|Commercial Banking
966|Lindah Gakii Murithi|Branch Operations Officer|Commercial Banking
967|Faith Moraa Nyagero|Service Assistant, Operations|Operations & Technology
968|Honest John Atibu|Customer Service Manager|Commercial Banking
970|Wanjora Kamau|Branch Operations Officer|Commercial Banking
972|Vera Cheruto Rono|Branch Operations Officer|Commercial Banking
973|George Anyona Patroba|Branch Operations Officer|Commercial Banking
982|Milcah Wambui Mwangi|Branch Operations Officer|Commercial Banking
984|Kipkorir Ngeno|Service Assistant Operations Officer|Operations & Technology
986|Richard Ogato Momanyi|Branch Operations Officer|Commercial Banking
987|Kingsley Efedi Onyia|Tax Advisor, EAC|Finance
988|Eva Yvonne Oyando|Branch Operations Officer|Commercial Banking
990|Jacinta Mbaki Makau|Branch Operations Officer|Commercial Banking
994|Nelson Muguna Kiambi|Bancassurance Officer|Consumer Banking
995|Sharon Osimbo Ombonya|Remedial Officer|Credit Risk Management
998|John Nzau Mwonga|Head, EWRR Kenya & EAC|Credit Risk Management
1014|Pius Muchangi|Head, EBS|Operations & Technology
1015|Dorcas Cherotich Siwatum|Service Assistant Operations Officer|Operations & Technology
1019|Kevin Kithinji Murithi|Senior Treasure Sales Officer|Treasury
1020|Elizabeth Waithegeni Kioi|Head Contact Centre & Complaints Management|Customer Experience
1026|Rene Musyoki Wambua|Branch Operations Officer|Commercial Banking
1028|Everlyne Wanjiku Gachago|Social Medial Officer|MD's Office
1031|Lazaro Muriuki Kariara|Branch Operations Officer|Commercial Banking
1032|Ursula Wanjira Muthee|Branch Operations Officer|Commercial Banking
1034|Loise Wanjiku Gachigua|Corporate Credit Analyst|Corporate Banking
1039|Sharleen Njeri Alli|Branch Operations Officer|Commercial Banking
1044|Esther Nkatha Mwirigi|Branch Operations Officer|Commercial Banking
1046|Florence Wambui Muhia|Personal Assistant|MD's Office
1048|Maryanne Nanjala Simiyu|Branch Operations Officer|Commercial Banking
1049|Samuel Mutisya Kavilu|Contact Center Agent|Customer Experience
1055|Purity Chepkorir Ronoh|CAD Officer|Credit Risk Management
1057|Rachael Koki Mbili|Team Leader, Payments RPC & Remittances|Operations & Technology
1060|Stanley Kimeli Birech|Channels Implementation Manager|Corporate Banking
1084|James Ngewa Muthoka|Contact Center Agent|Customer Experience
1090|David Otieno Omolo|Branch Operations Officer|Commercial Banking
1094|Vivian Kwamboka Ochako|Contact Center Agent|Customer Experience
1095|Faith J. Ellies|Contact Center Agent|Customer Experience
1100|Edna Adhiambo Odera|Branch Operations Officer|Commercial Banking
1106|Brenda Awuor Bolo|Service Assistant Operations Officer|Operations & Technology
1108|John Wambugu Wangeci|Senior Legal Officer|Legal
1110|Joel Kamatu Kiarie|Investigations Manager|Internal Audit
1112|Kelvin Kyulu|Channels Implementation Officer|Corporate Banking
1113|Joseph Onyango Odipo|Regional Head Remedial CESA|Credit Risk Management
1117|Joel Amenya Kiyondi|Information Systems Controller|Internal Control
1119|Winnie Achieng|Branch Operations Officer|Commercial Banking
1121|Kelvin Baraka Oketch|Trade Middle Office Officer|Corporate Banking
1124|Brenda Karimi Gitonga|Branch Operations Officer|Commercial Banking
1129|Tobias Felix Oduor|Branch Operations Officer|Commercial Banking
1131|Dennis Onyango Ndonji|Branch Operations Officer|Commercial Banking
1132|Emmanuel Kaptalai|Compliance Officer|Compliance
1133|Francis Muturi Wambui|Branch Operations Officer|Commercial Banking
1134|Roselyne Atieno Butt|Branch Operations Officer|Commercial Banking
1136|Lunar Magero|Head of Sales|Consumer Banking
1138|Patrick Kivuva|Archivist|Credit Risk Management
1141|Mohamed Souleymane|Director, Treasury & FICC, EAC|Treasury
1148|Diana Mukami Kaaria|Branch Operations Officer|Commercial Banking
1150|Sandra Virginia Shibichila|Branch Operations Officer|Commercial Banking
1151|Emmanuel Kipkirui Rotich|Internal Control Officer|Internal Control
1153|Grace Wanjiru Rubia|Branch Operations Officer|Commercial Banking
1154|Macklin Achieng Ochieng|Branch Operations Officer|Commercial Banking
1158|Jane Jelagat Atugah|Head, Product Segment Marketing & Distribution|Consumer Banking
1159|Robert Githaiga Maingi|Head, Digital Channels & Agency Network|Consumer Banking
1162|Brian Mmami Bulimo|Branch Operations Officer|Commercial Banking
1170|Pauline Wangari Wacheru|Branch Operations Officer|Commercial Banking
1172|Oscar Owuor Odiemo|Digital sales Officer|Corporate Banking
1173|Chrispinus Juma Masika|Branch Operations Officer|Commercial Banking
1174|Msellem Ali Omar|Branch Operations Officer|Commercial Banking
1175|George Sakwa Atsulu|Branch Operations Officer|Commercial Banking
1183|Peter Maina Ndere|Agency Manager|Consumer Banking
1186|Francis Otieno Onyango|EBS Officer|Operations & Technology
1187|Betty Chelagat Keter|Relationship Officer|Consumer Banking
1189|Edward Mwenda|Relationship Manager, Premier Banking|Consumer Banking
1191|Anna Wang Huan|Head, Chinese Desk|Corporate Banking
1192|Joshua Debarge Mwatibo|Branch Operations Officer|Commercial Banking
1194|Victor Njagi Ndambiri|Service Availability Officer|Operations & Technology
1195|Ken Maina Mwangi|ALM Officer|Treasury
1199|Nancy Waithira Mwai|HR Officer|Human resources
1202|Erick Bundi Kirimi|Branch Operations Officer|Commercial Banking
1204|Michael Maina Ngugi|Relationship Manager - SME|Commercial Banking
1205|Joshua Kiprop Tarbei|Contact Center Agent|Customer Experience
1206|Caroline Njoki Nyoro|Branch Operations Officer|Commercial Banking
1207|Lynnette Awuor Otieno|Team Leader, Payments RPC & Remittances|Operations & Technology
1209|Leonard Kipkoech Ngeno|Contact Center Agent|Customer Experience
1210|Lynne Wambui Maina|Litigation Officer|Legal
1211|Brian Ambuka|Operations Assistant Officer|Operations & Technology
1214|Linet Naisenya Kamami|Scheme Administrator Officer|Consumer Banking
1215|Kelvin Mutonga Wachira|Contact Center Agent|Customer Experience
1217|Gladys Mutanu Vundi|Manager, Partnership, Alliances & Diaspora|Consumer Banking
1218|Dennis Michael Ojiambo|Branch Manager|Commercial Banking
1219|Justus Kimutai Korir|Credit Risk Manager|Credit Risk Management
1223|Josphat Nyaberi Gichana|Relationship Manager|Consumer Banking
1224|Simon Kamau Gatonye|Relationship Manager|Consumer Banking
1225|Jean Wathoni Ng'ang'a|Operations Manager, Cards, Mobile & Digital Products|Operations & Technology
1227|Hildah Wambani Munoko|Operations Controls Officer|Operations & Technology
1228|James Chisakane Odera|Relationship Manager|Consumer Banking
1229|Erick Ochieng Ouma|Relationship Officer|Consumer Banking
1230|Shen Xue PEI|Relationship Manager|Corporate Banking
1233|Catherine Wanjiku Njoroge|Contact Center Agent|Customer Experience
1237|Michael Muriu Kinuthia|FX Trader|Treasury
1238|Amon Onduso Ogendo|Relationship Manager, SME|Commercial Banking
1240|Raphael Wambua Kivati|Acquiring Manager, EAC & Cash Product Manager Kenya|Corporate Banking
1241|Joseph Mutua Mumo|Cards Operations Officer|Operations & Technology
1243|Obed Mogaka Ogeto|Relationship Officer, Ellevate Desk|Commercial Banking
1244|Jackline Akinyi Ajock|Relationship Manager,SME|Commercial Banking
1245|Anne Waguthii Mureithi|Director Compliance- CESA 1|Compliance
1249|Carolyne Waithira Kamande|Service Assistant Operations Officer|Operations & Technology
1250|Felix Odiwuor Ouma|Officer Operations|Operations & Technology
1251|Paul Macharia Kirega|Credit Administration Officer|Credit Risk Management
1252|Livingstone Maina Kagio|Head , Local Corporates|Commercial Banking
1253|Ian Otieno Onyango|Reconciliations Officer|Internal Control
1255|Louis Orwa|Cards Operations Officer|Operations & Technology
1256|Peter Omondi Ogwenya|Operations Officer|Operations & Technology
1258|Collins F. Oloo|IT Officer|Operations & Technology
1259|Diana Mutanu|Compliance Officer|Compliance
1261|Stephen Kagiri Kimuyu|Relationship Manager, Employee Schemes|Consumer Banking
1262|Glory Kendi|Relationship Officer|Consumer Banking
1264|Hassanali Mudukiza|Acquiring Officer|Corporate Banking
1265|Cyprian Kiprotich Rono|Director, Corporate Banking Kenya & EAC|Corporate Banking
1266|Shadrack Mwongela Musyoki|Senior Internal Controller|Internal Control
1269|Fiona Nanetia Lein|Head Premier Banking|Consumer Banking
1270|Bellah Njeri Muriuki|Relationship Manager, Public Sector|Commercial Banking
1271|Gilbert Ariemo|Country Risk Manager, Kenya & EAC|Risk
1272|Francis Kamau Gathecha|Contact Center Agent|Customer Experience
1273|Moses Mwange Muasya|Financial Crime Compliance Manager|Compliance
1274|Florence Kabona|Branch Operations Officer|Commercial Banking
1276|Joseph Aloice Machi|Branch Operations Officer|Commercial Banking
1278|Patrick Solomon Guda|Contact Center Agent|Customer Experience
1279|Rose Wangari Munene|Contact Center Agent|Customer Experience
1281|Upendo Mutave Wambua|Head, SME|Commercial Banking
1282|Alex Odanga Ochieng|Credit Administration Officer|Credit Risk Management
1284|Kennedy Libibi Manyala|Head of Operations|Operations & Technology
1285|Jackson Nyakang'o|Relationship Officer|Consumer Banking
1286|Viginia Wangui Waweru|Relationship Officer|Consumer Banking
1287|Felix Deku|Regional Business Manager-CESA|MD's Office
1288|Griffin Muendo William|Relationship Manager, Local Corporate|Commercial Banking
1289|Geoffrey Simiyu Wanjala|Branch Manager|Commercial Banking
1291|Christine Kerubo Makone|Senior Relationship Manager, Public Sector|Corporate Banking
1292|Job Wepukhulu Sudi|Trade Sales Manager|Corporate Banking
1293|Jaffrson Orenge Nyakagwa|Relationship Manager, Regional Corporates|Corporate Banking
1295|George Tak Simel|Relationship Manager FI & IO|Corporate Banking
1296|Jane Nyawira Gachagi|Relationship Manager|Consumer Banking
1297|Robert Kiprotich Bett|Manager, Business Finance & Performance Management|Finance
1298|Humphrey Omondi Obiero|Business Analyst|Finance
1300|Catherine Mwikali Mutisya|Credit Analyst|Consumer Banking
1301|Susan Wanza Odhiambo|Relationship Officer|Consumer Banking
1302|Arnold Murimi Ngure|Senior Relationship Manager, Local Corporates|Commercial Banking
1303|Faith Ambiyo Essendi|Finance Officer|Finance
1304|Kelvin Mwendwa Muthoka|Operations Assistant Officer|Operations & Technology
1305|Brian Ong'era Ontita|Credit Analyst|Commercial Banking
1306|Benter Atieno|Value Chain Manager|Commercial Banking
1307|Marieanne Ebby Kadatz Wanzare|Relationship Manager, Local Corporate|Commercial Banking
1308|Christine Mbukuli Omucheni|EBS Officer|Operations & Technology
1309|Juliet Kinya Gitonga|Corporate Communications Manager|MD's Office
1310|Lydiah Kakuvi Musyoki|Relationship Manager, SME|Commercial Banking
1312|Sanchez Logan Madara|Branch Operations Officer|Commercial Banking
1313|Alfred Muthomi Miriti|Portfololio Analysis & Reporting Manager|Credit Risk Management
1314|Mirriam Mueni Muema|Business Development Officer, Bancassurance|Consumer Banking
1315|George Nyamai Jimmy|Corporate Credit Analyst|Corporate Banking
1316|Philiph Kimutai Ngetich|Relationship Manager, SME|Commercial Banking
1317|Richard Nzioka|Branch Manager|Commercial Banking
1318|Edwin Nyamenia Araka|Relationship Officer|Consumer Banking
1319|Esther Wambui Mbano|Asset Product Manager|Consumer Banking
1320|David Muriithi Mathenge|Manager, Bancassurance|Consumer Banking
1321|Calvin Abondo Oyugi|Senior Internal Auditor|Internal Audit
1323|Stephen Mutiku Kyalo|Information Systems Auditor|Internal Audit
1324|Wahiu Waciira|Head, Cash Management|Corporate Banking
1325|Chilson Indatula Vidolo|Market Risk Manager|Risk
1328|Angela Kinya Gitonga|Software Developer|Operations & Technology
1330|Jenipher Anyango Dola|Relationship Manager|Consumer Banking
1333|Rabecca Mueni Mbithi|Managing Director|MD's Office
1334|Ian Odiwuor Were|Relationship Manager|Commercial Banking
1335|Geoffrey Kerandi Onywoki|Relationship Manager, SME|Commercial Banking
1339|Emmanuel Akaka Okumu|Card Officer|Consumer Banking
1340|Mathew Kyalo Mutisya|Relationship Manager|Commercial Banking
1341|Vincent Gitonga Maina|Relationship Manager|Commercial Banking
1342|Carolyne Nashipae Adewunmi|Branch Manager|Commercial Banking
1343|Joan Jerono Sang|Relationship Officer|Consumer Banking
1344|Kennedy Luseno Voreza|Relationship Manager|Commercial Banking
1346|Grace Kinya Miriti|Asset & Liabilities Management Officer|Treasury
1347|Joshua Onyancha Mokua|Business Manager|MD's Office
1348|Dennis Mwangi Mutiga|Credit Analyst|Commercial Banking
1349|Faith Chepkemoi Yego|Branch Manager|Commercial Banking
1350|Beatrice Mwende Nzuve|Relationship Manager|Commercial Banking
1351|Linnet Wangui Waiharo|Contact Center Agent|Customer Experience
1352|Eric Odhiambo Onyango|Branch Operations Officer|Commercial Banking
1353|Ian Mulonzia Kilonzo|Branch Operations Officer|Commercial Banking"""

DSA = """CN112|Caroline Taabu Were|Team Leader|Plaza 2000
CN24|Monicah Nyambura Wanjohi|Intermediate DSA|Ecobank Towers
CN103|Rita Binsari Nyasente|Intermediate DSA|Ecobank Towers
CN21|Judith Akeng'o|Senior DSA|Eldoret
CN26|Patrick Kichwen|Intermediate DSA|Eldoret
CN27|Pauline Atieno Odhiambo|Team Leader|Kisumu
CN29|Roselyne Akoth Ochanda|Standard DSA|Kisumu
CN155|Minica Ogachi|Intermediate DSA|Kisumu
CN160|Elizabeth Khasiani Acham|Intermediate DSA|Eldoret
CN159|Faith Jepkogei|Senior DSA|Eldoret
CN17|Jackson Kipkogei Kipchoge|Team Leader|Eldoret
CN020|Josephat Mutwiri|Team Leader|Ecobank Towers
CN202|Topister Akinyi Musumba|Intermediate DSA|Westlands
CN205|Billy Owiny Ochieng|Intermediate DSA|Kisumu
CN207|Victor kibiwot Kibet|Intermediate DSA|Fortis
CN208|BRIAN MBUGUA OGUTU|Standard DSA|Karatina
CN212|Dinah Nekesa Makokha|Intermediate DSA|Nakuru
CN214|Grace Nkirote|Intermediate DSA|The Hub Branch
CN216|Brian Gitari|Standard DSA|The Hub Branch
CN220|Vivian Wairimu Mwaura|Standard DSA|Thika
CN223|Stella Nyaguthii Murithi|Standard DSA|Plaza 2000
CN224|Kelvin Kipruto Kimaiyo|Standard DSA|Nakuru
CN225|Everline Jerusa|Standard DSA|Plaza 2000
CN254|Moureen Kathure Runogone|Standard DSA|Eldoret
CN255|Nerryne Akinyi|Standard DSA|Eldoret
CN256|Dominic Ngetich Kipkurui|Standard DSA|Eldoret
CN257|Violah Biwott Jepkorir|Standard DSA|Eldoret
CN201|Antony Ndirangu Gichuhi|Standard DSA|Thika
CN262|Elizabeth Nyambura Waweru|Bancassurance Sales Officer|Westlands
CN263|Dorine Kerubo Nyamwaro|Bancassurance Sales Officer|Ecobank Towers
CN269|Yvonne Mukhaye|Bancassurance Sales Officer|The Hub Branch
CN270|Naftal Onchiri Nyakundi|Bancassurance Sales Officer|Kisii
CN277|Leakey Omondi|Standard DSA|Plaza 2000
CN278|Walter Okoth|Standard DSA|Plaza 2000
CN280|Stephine Owuor|Standard DSA|Ecobank Towers
CN281|Mercy Achieng Nange|Standard DSA|Karen
CN282|Emily Papa|Standard DSA|Plaza 2000
CN283|Naomi Kate Maina|Standard DSA|Westlands
CN284|Emmanuel Ogo Jilani|Standard DSA|Kisumu
CN285|Nancy Stecy Akinyi|Standard DSA|Kisumu
CN288|Sharon Anyango|Standard DSA|Valley Arcade
CN289|Ruth Wangari Chege|Standard DSA|Westlands
CN290|Diana Okeyo|Standard DSA|Eldoret
CN291|Silas Kiprotich Chirchir|Standard DSA|Eldoret
CN292|Seth Mokaya|Standard DSA|Kisii
CN293|Mercy Nasimiyu Kundu|Standard DSA|Plaza 2000
CN190|Eric Mbatha Mukwilu|Intermediate DSA|The Hub Branch
CN48|Ann Kinya Jeremiah|Team Leader|Westlands
CN243|NDWIGA MERCY WANJIKU|Standard DSA|Plaza 2000
CN245|ONDIGI OBWOGE ALBERT|Team Leader|Kisii
CN246|MUTATA RHODA KALIMI|Standard DSA|Kisii
CN251|KABENA IRENE MUTHONI|Standard DSA|The Hub Branch
CN297|Sharon Jeptoo Sitienei|Standard DSA|Eldoret
CN298|Emmanuel Otieno Abongo|Standard DSA|Kisumu
CN299|Nancy Jepchoge|Standard DSA|Eldoret
CN300|Stephine Lwali|Standard DSA|Eldoret
CN301|Jared Oluoch Ouko|Standard DSA|Ecobank Towers
CN302|Concepta Mutauta|Standard DSA|Ecobank Towers
CN303|Doreen Wawira|Standard DSA|Fortis
CN304|Lynet Mutheu|Standard DSA|Mombasa
CN305|Vivian Moraa|Standard DSA|Mombasa
CN306|Michael Obiero Sijenyi|Standard DSA|Karatina
CN307|Brian Sagini Ogeto|Standard DSA|Karen
CN308|Shadrack Cheruiyot Kirui|Standard DSA|Plaza 2000
CN309|Shalom Wanjiku Thumbi|Standard DSA|Plaza 2000
CN310|Kezia Moraa|Standard DSA|Fortis
CN312|Steven Omondi Ongoje|Standard DSA|Kisumu
CN314|Amina Awuor Saad|Standard DSA|The Hub Branch
CN315|George Mbinda Mutua|Standard DSA|Industrial Area
CN317|Perpetua Nana Kauma|Bancassurance Sales Officer|Karen
CN319|James Mung'ei Mwangi|Bancassurance Sales Officer|Nyeri
CN320|Christine Akinyi Omondi|Bancassurance Sales Officer|Nakuru
CN322|Alex Kibet Serem|Bancassurance Sales Officer|Eldoret
CN324|Catherine Ombogi|Standard DSA|Thika
New|Felix Kirui Kimutai|Standard DSA|Nakuru
New|Virginia Wandia|Standard DSA|Nakuru
New|Hillary Kiprotich Yegon|Standard DSA|Eldoret
New|Kelvin Mthoni|Standard DSA|Karatina
New|Maureen Chemurgor|Standard DSA|Kisii
New|Kenneth Kirundu Orende|Standard DSA|Plaza 2000
New|Faith Chepchirchir|Standard DSA|Plaza 2000
New|Audry Teresa Ochieng|Standard DSA|Kisii
New|Dancun Otieno Odhiambo|Standard DSA|Kisii
New|Don Obengo|Standard DSA|Kisumu
New|Larisa Mongare|Standard DSA|Kisii
New|Lydiah Bangweso|Standard DSA|Kisii
New|Emily Lily Atieno|Standard DSA|Kisumu
New|Samuel Mbogo|Standard DSA|Valley Arcade
New|Philip Ichomi|Standard DSA|Karen
New|Boniface Okwero|Standard DSA|Thika
New|Sharon Anyango Omondi|Standard DSA|Kisii
New|Lilian Mutua Gemina|Standard DSA|Ecobank Towers
New|Susan Nyatichi Monari|Standard DSA|Kisii
New|Norah Mumo Wambua|Standard DSA|Ecobank Towers
New|Marion Jepkorir|Standard DSA|Eldoret
New|Mark Munene|Standard DSA|Upper Hill
New|Hellen Auma Ogilo|Standard DSA|Plaza 2000
New|Jacinta Sopiato|Standard DSA|Nakuru
New|Priscilla Nyakio|Standard DSA|Nakuru
New|Pauline Kaingi Kusa|Standard DSA|Mombasa
New|Alex Musau Kisese|Standard DSA|Nakuru
New|Elizabeth Akinyi Apiyo|Standard DSA|Kisumu"""

def main():
    import pandas as pd
    os.makedirs("data", exist_ok=True)
    p = [r.split("|") for r in PERM.strip().split("\n")]
    d = [r.split("|") for r in DSA.strip().split("\n")]
    bad = [r for r in p + d if len(r) != 4]
    if bad:
        print("malformed rows:", bad[:3]); sys.exit(1)
    pd.DataFrame(p, columns=["Staff Number", "Name of Staff", "Designation", "Department"]) \
        .to_excel("data/staff_source_permanent.xlsx", index=False)
    pd.DataFrame(d, columns=["Staff Number", "Name", "Title", "Branch"]) \
        .to_excel("data/staff_source_dsa.xlsx", index=False)
    print(f"wrote data/staff_source_permanent.xlsx  ({len(p)} rows)")
    print(f"wrote data/staff_source_dsa.xlsx        ({len(d)} rows, "
          f"{sum(1 for r in d if r[0]=='New')} pending recruitment)")
    print("\nNEXT:  python ingest_staff.py")

if __name__ == "__main__":
    main()
