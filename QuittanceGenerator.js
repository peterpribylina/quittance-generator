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

    doc.image("./img/logo-coloc-watermark.png", 410, 410, {
      fit: [500, 500],
      align: "center",
      valign: "bottom",
    });

    doc
      .font(`${fontName + "-Bold"}`)
      .text("Quittance de loyer", beginningOfPage, 210, {
        align: "center",
      })
      .text(
        `Loyer ${this.quittance.period.periodMMMYY}`,
        beginningOfPage,
        225,
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

    doc
      .moveTo(beginningOfPage - 10, 660)
      .lineTo(endOfPage + 10, 660)
      .lineWidth(1)
      .stroke();

    doc
      .fontSize(10)
      .text(
        `Reçu de : ${
          this.quittance.client.title
        }. ${this.quittance.client.fullName.split(" ")[1].toUpperCase()} ${
          this.quittance.client.fullName.split(" ")[0]
        }`,
        beginningOfPage,
        270,
        {
          align: "left",
          width: 250,
        }
      )
      .text(`la somme de `, beginningOfPage, 300, {
        align: "left",
        width: 250,
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.total} €`, beginningOfPage, 300)
      .font(fontName)
      .text(`le `, beginningOfPage, 330, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.paymentDate}`)
      .font(fontName)
      .text(
        `pour loyer et accessoires des locaux situés au:  `,
        beginningOfPage,
        360,
        {
          width: 250,
          continued: true,
        }
      )
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.client.adresse}`)
      .font(fontName)
      .text(`en paiement du terme du mois `, beginningOfPage, 410, {
        align: "left",
        continued: true,
      })
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

    /* right column */
    doc
      .font(`${fontName + "-Bold"}`)
      .fontSize(10)
      .text(`Détail :`, beginningOfPageCol2, 270, {
        align: "left",
        width: 250,
      })
      .font(fontName)
      .text(`- Loyer nu : `, beginningOfPageCol2, 300, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.rent} €`)
      .font(fontName)
      .text(`- Provisions de charges : `, beginningOfPageCol2, 330, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.charges} €`)
      .font(fontName)
      .text(`Montant total du terme : `, beginningOfPageCol2, 390, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.total} €`)
      .font(fontName)
      .text(`- Paiement locataire : `, beginningOfPageCol2, 420, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`${this.quittance.total} €`)
      .font(fontName)
      .text(`- Solde à payer : `, beginningOfPageCol2, 450, {
        continued: true,
      })
      .font(`${fontName + "-Bold"}`)
      .text(`0 €`);
  }

  generateFooter(doc) {
    doc
      .fontSize(8)
      .font(fontName)
      .fillColor("grey")
      .text(
        `Le paiement de la présente n'emporte pas présomption de paiement des termes antérieurs. Cette quittance ou ce reçu annule tous les reçus qui auraient pu être donnés pour acompte versé sur le présent terme. En cas de congé précédemment donné, cette quittance ou ce reçu représenterait l'indemnité d'occupation et ne saurait être considéré comme un titre d'occupation. Sous réserve d'encaissement.`,
        beginningOfPage,
        690,
        {
          align: "center",
          width: 500,
        }
      );
  }

  generate() {
    let theOutput = new PDFGenerator();

    const fileName = `Quittance_de_loyer_${
      this.quittance.client.fullName.split(" ")[0]
    }_${this.quittance.client.fullName.split(" ")[1].toUpperCase()}_${
      this.quittance.period.periodYYYYMM
    }.pdf`;

    const fullLocalFilename = path.join(
      this.quittance.client.localFolderPath,
      this.quittance.client.fullName.replace(/ /g, "_"),
      "Quittances",
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
      console.info("Quittance already created :)");
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
        subject: `Quittance de loyer - ${this.quittance.period.periodMMMYY} ✔`,
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
