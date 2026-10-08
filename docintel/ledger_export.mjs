// Public artifact-tool API only. Modules may be installed separately or supplied by Codex.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const [source,target,modules]=process.argv.slice(2);
const require=createRequire(path.join(modules,'..','ledger-loader.cjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool',{paths:[modules]})).href);
const data=JSON.parse(await fs.readFile(source,'utf8'));
const wb=Workbook.create();
const overview=wb.worksheets.add('Overview');
const receipts=wb.worksheets.add('Receipts');
const purchases=wb.worksheets.add('Purchases');
const safe=value=>typeof value==='string'&&/^[=+@-]/.test(value)?"'"+value:value;
function build(sheet,title,notes,headers,rows,name,dateColumns,moneyColumns){
  sheet.showGridLines=false;
  const width=headers.length,last=String.fromCharCode(64+width),end=Math.max(7,rows.length+6);
  sheet.getRange(`A1:${last}${end}`).format.font={name:'Arial',size:10,color:'#243746'};
  sheet.getRange(`A1:${last}${end}`).format.columnWidth=18;
  sheet.getRange('A1:H1').merge();sheet.getRange('A1').values=[[title]];
  sheet.getRange('A1:H1').format.font={name:'Arial',size:14,bold:true,color:'#0F766E'};
  sheet.getRange('A2:H3').merge();sheet.getRange('A2').values=[[notes]];sheet.getRange('A2:H3').format.wrapText=true;
  const matrix=[headers,...(rows.length?rows.map(r=>r.map(safe)):[headers.map(()=>null)])];
  sheet.getRange(`A6:${last}${end}`).values=matrix;
  sheet.tables.add(`A6:${last}${end}`,true,name);
  sheet.getRange(`A6:${last}6`).format={fill:'#0F766E',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:32};
  sheet.getRange(`A7:${last}${end}`).format.rowHeight=30;
  sheet.getRange(`C6:D${end}`).format.columnWidth=28;
  sheet.getRange(`D7:D${end}`).format.wrapText=true;
  for(const col of dateColumns){
    const index=col.charCodeAt(0)-65;
    rows.forEach((r,i)=>{if(typeof r[index]==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(r[index]))sheet.getRange(`${col}${i+7}`).values=[[new Date(r[index]+'T00:00:00Z')]];});
    sheet.getRange(`${col}7:${col}${end}`).setNumberFormat('dd-mmm-yyyy');
  }
  for(const col of moneyColumns)sheet.getRange(`${col}7:${col}${end}`).setNumberFormat('#,##0.00;[Red](#,##0.00);0.00');
  sheet.freezePanes.freezeRows(6);sheet.freezePanes.freezeColumns(3);
}
build(receipts,'Household purchase ledger','App-managed workbook. Make corrections in Evidence Ledger. Pending readings are retained; confirmed costs exclude them. Currencies stay separate.',
 ['Member','Purchase date','Merchant','Receipt number','Currency','Read total','Confirmed total','Date review','Receipt status','Next step','Photos','Receipt key','Document ID'],data.receipts,'HouseholdReceipts',['B'],['F','G']);
receipts.getRange(`J6:J${Math.max(7,data.receipts.length+6)}`).format.columnWidth=45;
receipts.getRange(`J7:J${Math.max(7,data.receipts.length+6)}`).format.wrapText=true;
receipts.getRange('L:M').format.columnWidth=12;
build(purchases,'What the household bought','Each row is a printed line. Discounts, tax and payments retain their line type. Never add item costs to receipt totals or multiply line amounts by quantity.',
 ['Member','Purchase date','Merchant','Item','Category','Quantity','Current line cost','Currency','Item review','Confirmed line cost','Line type','Unit price','Receipt status','Printed description','Product code','Photo','Line key','Document ID'],data.items.map(r=>[0,1,2,3,4,5,7,9,11,8,10,6,12,13,14,15,16,17].map(i=>r[i])),'HouseholdPurchases',['B'],['G','J','L']);
purchases.getRange('E:E').format.columnWidth=27;
purchases.getRange('Q:R').format.columnWidth=12;
overview.showGridLines=false;
overview.getRange('A1:D20').format.font={name:'Arial',size:10,color:'#243746'};
overview.getRange('A:A').format.columnWidth=28;overview.getRange('B:D').format.columnWidth=26;
overview.getRange('A1:D1').merge();overview.getRange('A1').values=[['Household spending']];
overview.getRange('A1').format.font={name:'Arial',size:14,bold:true,color:'#0F766E'};
overview.getRange('A3:B5').values=[['Receipts captured',data.receipts.length],['Receipts needing review',data.needs_review],['Items captured',data.items.length]];
overview.getRange('A7:B7').values=[['Currency','Confirmed receipt spending']];
overview.getRange('A7:B7').format={fill:'#0F766E',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:30};
if(data.totals.length){
 data.totals.forEach((t,i)=>{overview.getRange(`A${i+8}`).values=[[t.currency]];overview.getRange(`B${i+8}`).formulas=[[`=SUMIF(Receipts!E7:E${Math.max(7,data.receipts.length+6)},A${i+8},Receipts!G7:G${Math.max(7,data.receipts.length+6)})`]];});
 overview.getRange(`B8:B${data.totals.length+7}`).setNumberFormat('#,##0.00');
}else overview.getRange('A8:B8').values=[['No confirmed spending',null]];
const noteRow=Math.max(11,data.totals.length+10);
overview.getRange(`A${noteRow}:D${noteRow+2}`).merge();overview.getRange(`A${noteRow}`).values=[['Pending readings are visible in Receipts and Purchases. Confirmed totals count eligible receipts once, in their original currency. Buyer names are self-declared. Correct readings in the app; workbook edits are replaced on the next update.']];overview.getRange(`A${noteRow}:D${noteRow+2}`).format.wrapText=true;overview.getRange(`A${noteRow}:D${noteRow+2}`).format.rowHeight=28;
wb.recalculate();
for(let i=0;i<data.totals.length;i++){
 const value=overview.getRange(`B${i+8}`).values[0][0];
 if(typeof value!=='number'||Math.abs(value-Number(data.totals[i].total))>0.005)throw new Error('Workbook total check failed');
}
if(process.env.LEDGER_PREVIEW_DIR){
 await fs.mkdir(process.env.LEDGER_PREVIEW_DIR,{recursive:true});
 for(const sheetName of ['Overview','Receipts','Purchases']){
  const image=await wb.render({sheetName,range:sheetName==='Overview'?'A1:D16':'A1:J12',scale:1.5,format:'png'});
  await fs.writeFile(path.join(process.env.LEDGER_PREVIEW_DIR,sheetName+'.png'),new Uint8Array(await image.arrayBuffer()));
 }
 await fs.writeFile(path.join(process.env.LEDGER_PREVIEW_DIR,'inspection.txt'),(await wb.inspect({kind:'region',sheetId:'Receipts',range:'A1:J12',maxChars:3000})).ndjson);
}
await (await SpreadsheetFile.exportXlsx(wb)).save(target);
