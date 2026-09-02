/**
 * node . period='2022-07' paymentDate=01/07/2022 quittanceNumber=11 rent=320.00 charges=80.00 client=Victor force=true && open Quittance\ de\ loyer\ Victor\ Lefebvre\ -\ 2022-07.pdf
 *
 *
 */
const PDFGenerator = require("pdfkit");
const fs = require("fs");
const path = require("path");

const fontName = "Helvetica";
const beginningOfPage = 60;
const beginningOfPageCol2 = beginningOfPage + 260;
const endOfPage = 550;

class QuittanceGenerator {
  constructor(quittance, forceCreation) {
    this.quittance = quittance;
    this.forceCreation = forceCreation;
  }

  generateHeaders(doc) {
    doc.fontSize(10).font(fontName);

    doc
      .text(`Bailleur`, beginningOfPage, 50, {
        align: "left",
      })
      .image("./img/logo-coloc.png", 500, 50, { width: 50 })
      .fillColor("#000")
      .moveDown()
      .text(`M. PRIBYLINA Peter`, beginningOfPage, 80, {
        align: "left",
      })
      .text(`21 rue Hélène Boucher`, beginningOfPage, 95, {
        align: "left",
      })
      .text(`59700 Marcq en Barouel`, beginningOfPage, 110, {
        align: "left",
      });

    /*

    doc
      .moveTo(beginningOfPage - 10, 200)
      .lineTo(beginningOfPage - 10, 660)
      .lineWidth(1)
      .stroke();

    doc
      .moveTo(beginningOfPage - 10, 200)
      .lineTo(endOfPage + 10, 200)
      .lineWidth(1)
      .stroke();

    doc
      .moveTo(endOfPage + 10, 200)
      .lineTo(endOfPage + 10, 660)
      .lineWidth(1)
      .stroke();

    doc
      .moveTo(beginningOfPage - 10, 200)
      .lineTo(endOfPage + 10, 200)
      .lineWidth(1)
      .stroke();

    doc
      .moveTo(beginningOfPage - 10, 255)
      .lineTo(endOfPage + 10, 255)
      .lineWidth(1)
      .stroke();

    doc.moveTo(310, 255).lineTo(310, 660).lineWidth(1).stroke();
    */

    doc.image("./img/logo-coloc-watermark.png", 410, 410, {
      fit: [500, 500],
      align: "center",
      valign: "bottom",
    });

    doc.font(`${fontName + "-Bold"}`).text(
      "ATTESTATION D'HÉBERGEMENT",
      beginningOfPage,
      210,
      {
        align: "center",
      }
      /*
      )
      .font(fontName)
      .fontSize(8)
      .text(`Quittance n°: ${this.quittance.quittanceNumber}`, {align: "right"}
      */
    );

    /*
    doc
      .moveTo(beginningOfPage - 10, 660)
      .lineTo(endOfPage + 10, 660)
      .lineWidth(1)
      .stroke();
  */

    doc
      .fontSize(10)
      .text(
        `Je soussigné Peter PRIBYLINA, né le 15 août 1978 à Banska Bystrica, SLOVAQUIE déclare sur l'honneur hébergé : `,
        beginningOfPage,
        270,
        {
          align: "left",
          width: 250,
        }
      )
      .text(
        `${this.quittance.client.title}. ${this.quittance.client.fullName
          .split(" ")[1]
          .toUpperCase()} ${this.quittance.client.fullName.split(" ")[0]},`,
        beginningOfPage,
        300,
        {
          align: "left",
          width: 250,
          continued: true,
        }
      )
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.total} €`, beginningOfPage, 300)
      .font(fontName)
      .text(
        `né ${this.quittance.client.birthdate} à ${this.quittance.client.birthcity} depuis le 1 septembre 2025 à l'adresse suivante : ${this.quittance.client.adresse}. `,
        beginningOfPage,
        330,
        {
          continued: true,
        }
      )
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.period.periodMMMYY}`)
      .font(fontName)
      .text(`Fait à Marcq en Baroeul le `, beginningOfPage, 470, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.period.todayDDMMYYYY}`)
      .font(fontName)
      .text(`Signature du bailleur `, beginningOfPage, 500);

    doc
      .image("./img/signature.png", beginningOfPage + 10, 520, { width: 140 })
      .fillColor("#000")
      .moveDown();
  }

  generate() {
    let theOutput = new PDFGenerator();

    const fileName = `Attestattion_hebergement.pdf`;

    const fullLocalFilename = path.join(
      this.quittance.client.localFolderPath,
      this.quittance.client.fullName.replace(/ /g, "_"),
      "Docs",
      fileName
    );

    let fileExists = fs.existsSync(fullLocalFilename);

    console.log(fullLocalFilename);
    if (!fileExists || this.forceCreation) {
      theOutput.pipe(fs.createWriteStream(fullLocalFilename));
      this.generateHeaders(theOutput);
      theOutput.moveDown();
      this.generateFooter(theOutput);
      // write out file
      theOutput.end();
      console.info("Document saved " + fullLocalFilename + " :)");
    } else {
      console.info("Attestation already created :)");
    }
    // pipe to a writable stream which would save the result into the same directory

    const nodemailer = require("nodemailer");

    const transporter = nodemailer.createTransport({
      service: "gmail",
      auth: {
        user: "peter.pribylina@gmail.com",
        pass: process.env.GMAIL_APP_PASSWORD,
      },
    });

    transporter
      .sendMail({
        from: '"Peter Pribylina" <peter.pribylina@gmail.com>',
        to: this.quittance.client.email,
        subject: `Attestation d'hébergement 2025 ✔`,
        text: `Bonjour ${
          this.quittance.client.fullName.split(" ")[0]
        },\nci-joint le documement.\n\nBien à toi, Peter`,
        html: `Bonjour ${
          this.quittance.client.fullName.split(" ")[0]
        },<br/><br/>ci-joint le document pour le mois de <b>${
          this.quittance.period.periodMMMYY
        }</b>.<br/><br/>Bien à toi,<br/>Peter`,
        attachments: [
          {
            filename: fileName,
            path: fullLocalFilename,
          },
        ],
      })
      .then((info) => {
        console.log({ info });
      })
      .catch(console.error);
  }
}

module.exports = QuittanceGenerator;
