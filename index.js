"use strict";

const {
  getSpreadSheetValues,
  createDocCopy,
  x,
} = require("./googleDriveService.js");

const { getClientRef, targetFileExistLocally } = require("./helper");
var path = require("path");
var moment = require("moment");

moment.locale("fr");

// ressources:
// https://github.com/googleapis/google-api-nodejs-client/blob/main/samples/drive/export.js
// https://docs.google.com/spreadsheets/d/1mDHIokVwX0z4c-NBmu4oayxZX-2Awo-ZdhCMmCzJd0Y/edit#gid=0

//const spreadsheetId = "1mDHIokVwX0z4c-NBmu4oayxZX-2Awo-ZdhCMmCzJd0Y";
//const baseTargetFileName = "Quittance de loyer";

const period = process.argv[2].split("=")[1];
const paymentDate = process.argv[3].split("=")[1];
/*const quittanceNumber = process.argv[4].split("=")[1];*/

const rent = process.argv[4].split("=")[1];
const charges = process.argv[5].split("=")[1];
const clientName = process.argv[6].split("=")[1];
//const forceCreation = process.argv[7].split("=")[1] === "true";
const forceCreation = true

if (period == undefined) {
  console.error("Wrong or missing priode supplied.");
  process.exit(1);
}

if (paymentDate == undefined) {
  console.error("Wrong or missing paymentDate supplied.");
  process.exit(1);
}

const clientRef = getClientRef(clientName);
const periodMMMYY = moment(period, "YYYY-MM");

const QuittanceGenerator = require("./QuittanceGenerator");

const quittanceData = {
  period: {
    periodYYYYMM: period,
    periodMMMYY: periodMMMYY.format("MMMM YYYY"),
    todayDDMMYYYY: moment().format("DD/MM/YYYY"),
  },
  /*quittanceNumber: quittanceNumber,*/
  client: clientRef,
  rent: rent,
  charges: charges,
  total: (parseFloat(rent) + parseFloat(charges)).toString(),
  paymentDate: paymentDate,
};

const quittance = new QuittanceGenerator(quittanceData, forceCreation);
quittance.generate();
