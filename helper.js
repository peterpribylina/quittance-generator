const fs = require("fs");
//const { path } = require("pdfkit");
const path = require("path");

/**
 * @see https://gist.github.com/westc/c8a08042d176600850a5e5cbc4c226e9
 * Takes a column name and returns the corresponding integer (eg. E becomes 5).
 * @param {string} columnName
 *     The column name (eg. A, B, C, ..., Z, AB, AC, etc.) to be converted to an
 *     integer.
 * @param {?boolean=} opt_isZeroBased
 *     Indicates if the returned number should be 0-based.  If 0-based "E" will
 *     become 4.
 * @return {number}
 *     The integer representing the column name.
 */
function toColumnNumber(columnName, opt_isZeroBased) {
  if (columnName == undefined) {
    console.error("Wrong or missing column supplied.");
    process.exit(1);
  }

  if (!/^[A-Z]+$/.test(columnName)) {
    console.error(
      "The column name to be parsed must be a string of one or more letters (A to Z)."
    );
    process.exit(1);
    /*
    throw new TypeError(
      "The column name to be parsed must be a string of one or more letters (A to Z)."
    );
    */
  }
  let number = 0;
  for (let i = columnName.length, j = 0; i--; j++) {
    number += Math.pow(26, i) * (columnName.charCodeAt(j) - 64);
  }
  return number - (opt_isZeroBased ? 1 : 0);
}

function getClientRef(name) {
  //const baseLocalUrl = ["/Users", "peter", "Documents", "perso", "Immo"]; on Mac
  const baseLocalUrl = [
    "C:",
    "Users",
    "P5073668",
    "Documents",
    "quittances",
  ];
  const Adresse = {
    Anzin: "3 impasse Lecomte, 59410 Anzin",
    Vals: "14 avenue de Condé, 59300 Valenciennes",
    Lille: "84 rue Jules Vallès, 59800 Lille",
  };

  const LocalFolderPath = {
    Anzin: [...baseLocalUrl, "Coloc_Anzin", "Locataires_Anzin"],
    Vals: [...baseLocalUrl, "Coloc_Vals", "Locataires_Vals"],
    Lille: [...baseLocalUrl, "Appart_Lille", "Location"],
  };

  switch (name) {
    case "Ismail":
      return {
        title: "M",
        fullName: "Ismail Boufeloussen",
        email: "ismailbouf60@gmail.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    case "Jin":
      return {
        title: "M",
        fullName: "Jingyi Luo",
        email: "ljy1060024162@gmail.com",
        adresse: Adresse.Anzin,
        localFolderPath: path.join(LocalFolderPath.Anzin.join("/")),
      };
    case "Zakath":
      return {
        title: "M",
        fullName: "Zakath Laville",
        email: "zakathlaville@gmail.com",
        adresse: Adresse.Anzin,
        localFolderPath: path.join(LocalFolderPath.Anzin.join("/")),
      };
    case "Matilde":
      return {
        title: "Mlle",
        fullName: "Matilde Aranibar Campero",
        email: "matildearanibarcampero@gmail.com",
        adresse: Adresse.Anzin,
        localFolderPath: path.join(LocalFolderPath.Anzin.join("/")),
      };
    case "Madina":
      return {
        title: "Mlle",
        fullName: "Madina Tazhbagambetova",
        email: "madinaqays@gmail.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    case "Alice":
      return {
        title: "Mlle",
        fullName: "Alice Rolland",
        email: "arolland904@gmail.com",
        adresse: Adresse.Anzin,
        localFolderPath: path.join(LocalFolderPath.Anzin.join("/")),
      };
    case "Xin":
      return {
        title: "Mlle",
        fullName: "XinXuan Li",
        email: "yxtk1797@163.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    case "Audrey":
      return {
        title: "M",
        fullName: "Audrey Gogoua",
        email: "klebienmaxime@yahoo.fr, audreygogoua05@icloud.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    /* Lille */
    case "Peter":
      return {
        title: "M",
        fullName: "Peter Pribylina",
        email: "peter.pribylina+qg@gmail.com", // peter.pribylina+lml@gmail.com
        adresse: Adresse.Lille,
        localFolderPath: path.join(LocalFolderPath.Lille.join("/")),
      };
    case "Mathias":
      return {
        title: "M",
        fullName: "Mathias Vanzieleghem",
        email: "math.vzhm@gmail.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    case "Henri":
      return {
        title: "M",
        fullName: "Henri Fournet",
        email: "fournethyou2008@gmail.com",
        adresse: Adresse.Vals,
        localFolderPath: path.join(LocalFolderPath.Vals.join("/")),
      };
    default:
      console.error("Wrong or missing client name supplied.");
      process.exit(1);
  }
}

function targetFileExistLocally(fileNameWithAbsolutePath) {
  try {
    console.log(fileNameWithAbsolutePath);
    if (fs.existsSync(fileNameWithAbsolutePath)) {
      return true;
    } else {
      return false;
    }
  } catch (err) {
    return false;
  }
}

module.exports = {
  toColumnNumber,
  getClientRef,
  targetFileExistLocally,
};
