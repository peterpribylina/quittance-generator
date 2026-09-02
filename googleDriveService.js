// googleSheetsService.js

const { google } = require("googleapis");
const credentials = require("./credentials.json");

const scopes = [
  "https://www.googleapis.com/auth/drive",
  "https://www.googleapis.com/auth/drive.file",
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/documents",
  "https://www.googleapis.com/auth/drive.appdata",
];

const auth = new google.auth.JWT(
  credentials.client_email,
  null,
  credentials.private_key,
  scopes
);

const drive = google.drive({ version: "v3", auth });
const sheets = google.sheets({ version: "v4", auth: auth });
const docs = google.docs({ version: "v1", auth: auth });

// log spreadsheet
const spreadsheetId = "1mDHIokVwX0z4c-NBmu4oayxZX-2Awo-ZdhCMmCzJd0Y";

// template id
const docId = "1C8ZKKQMDXfcH5VEr7ctDm6KadINTuk4Wu5TOrt7vc_Q";

async function x({ newName }) {
  console.log("creating file");
  const res = await drive.files
    .create({
      requestBody: {
        name: "00AA",
        mimeType: "text/plain",
      },
      media: {
        mimeType: "text/plain",
        body: "Hello World",
      },
    })
    .then((r) => {
      console.log("Then err: " + JSON.stringify(r));
    });
  //console.log("R data: " + res.data);
}

async function createDocCopy({ newName }) {
  var copyRequest = {
    name: newName,
    parents: ["1zycPmHYD8DDmNlFLKW_wkZZCP_e6Rxs7"],
  };

  drive.files.copy(
    {
      fileId: docId,
      requestBody: copyRequest, // or resource: copyRequest
    },
    function (err, response) {
      if (err) {
        console.log("ERRRRRRRRRR");
        console.log(err);
        return;
      }
      console.log(response);
    }
  );
}

async function getSpreadSheetValues({ spreadsheetId }) {
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId,
    auth,
    range: "Loyers!P:P",
  });
  return res;
}

module.exports = {
  getSpreadSheetValues,
  createDocCopy,
  x,
};
