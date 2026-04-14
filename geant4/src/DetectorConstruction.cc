#include "DetectorConstruction.hh"
#include "AirPetSensitiveDetector.hh"

#include "G4ElectroMagneticField.hh"
#include "G4FieldBuilder.hh"
#include "G4GenericMessenger.hh"
#include "G4GeometryManager.hh"
#include "G4LogicalVolume.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4ProductionCuts.hh"
#include "G4Region.hh"
#include "G4RegionStore.hh"
#include "G4RunManager.hh"
#include "G4SDManager.hh"
#include "G4PhysicalVolumeStore.hh"
#include "G4SolidStore.hh"
#include "G4UIcmdWith3VectorAndUnit.hh"
#include "G4UIdirectory.hh"
#include "G4UImessenger.hh"
#include "G4UserLimits.hh"
#include "G4SystemOfUnits.hh"

#include <algorithm>
#include <exception>
#include <fstream>
#include <sstream>
#include <vector>

namespace
{

class AirPetUniformElectroMagneticField : public G4ElectroMagneticField
{
public:
  AirPetUniformElectroMagneticField(const G4ThreeVector& magneticField,
                                    const G4ThreeVector& electricField)
    : fMagneticField(magneticField), fElectricField(electricField)
  {}

  void GetFieldValue(const G4double[4], G4double* field) const override
  {
    field[0] = fMagneticField.x();
    field[1] = fMagneticField.y();
    field[2] = fMagneticField.z();
    field[3] = fElectricField.x();
    field[4] = fElectricField.y();
    field[5] = fElectricField.z();
  }

  G4bool DoesFieldChangeEnergy() const override
  {
    return fElectricField.mag2() > 0.0;
  }

private:
  G4ThreeVector fMagneticField;
  G4ThreeVector fElectricField;
};

class AirPetGlobalFieldMessenger : public G4UImessenger
{
public:
  explicit AirPetGlobalFieldMessenger(DetectorConstruction* detector)
    : fDetector(detector)
  {
    fDirectory = new G4UIdirectory("/globalField/");
    fDirectory->SetGuidance("Global uniform electromagnetic field UI commands");

    fSetMagneticValueCmd = new G4UIcmdWith3VectorAndUnit("/globalField/setValue", this);
    fSetMagneticValueCmd->SetGuidance("Set uniform magnetic field value.");
    fSetMagneticValueCmd->SetParameterName("Bx", "By", "Bz", false);
    fSetMagneticValueCmd->SetUnitCategory("Magnetic flux density");
    fSetMagneticValueCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

    fSetElectricValueCmd = new G4UIcmdWith3VectorAndUnit("/globalField/setElectricValue", this);
    fSetElectricValueCmd->SetGuidance("Set uniform electric field value.");
    fSetElectricValueCmd->SetParameterName("Ex", "Ey", "Ez", false);
    fSetElectricValueCmd->SetUnitCategory("Electric field");
    fSetElectricValueCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
  }

  ~AirPetGlobalFieldMessenger() override
  {
    delete fSetMagneticValueCmd;
    delete fSetElectricValueCmd;
    delete fDirectory;
  }

  void SetNewValue(G4UIcommand* command, G4String newValue) override
  {
    if (command == fSetMagneticValueCmd) {
      fDetector->SetGlobalMagneticField(fSetMagneticValueCmd->GetNew3VectorValue(newValue));
    } else if (command == fSetElectricValueCmd) {
      fDetector->SetGlobalElectricField(fSetElectricValueCmd->GetNew3VectorValue(newValue));
    }
  }

private:
  DetectorConstruction* fDetector;
  G4UIdirectory* fDirectory = nullptr;
  G4UIcmdWith3VectorAndUnit* fSetMagneticValueCmd = nullptr;
  G4UIcmdWith3VectorAndUnit* fSetElectricValueCmd = nullptr;
};

bool ParseFieldAssignmentPayload(const G4String& assignmentPayload,
                                 const G4String& fieldLabel,
                                 const G4String& unitLabel,
                                 G4String& logicalVolumeName,
                                 G4ThreeVector& fieldVector)
{
  std::stringstream stream(assignmentPayload);
  std::string logicalVolumeText;
  std::string fieldXText;
  std::string fieldYText;
  std::string fieldZText;

  if (!std::getline(stream, logicalVolumeText, '|') || !std::getline(stream, fieldXText, '|') ||
      !std::getline(stream, fieldYText, '|') || !std::getline(stream, fieldZText, '|')) {
    G4cerr << "--> WARNING: Invalid local " << fieldLabel << " field payload '"
           << assignmentPayload << "'. Expected <LogicalVolumeName>|<FieldX>|<FieldY>|<FieldZ>."
           << G4endl;
    return false;
  }

  try {
    const G4double fieldX = std::stod(fieldXText);
    const G4double fieldY = std::stod(fieldYText);
    const G4double fieldZ = std::stod(fieldZText);

    logicalVolumeName = logicalVolumeText;
    fieldVector = G4ThreeVector(fieldX, fieldY, fieldZ);
    G4cout << "--> Requested local " << fieldLabel << " field (" << fieldX << ", " << fieldY
           << ", " << fieldZ << ") " << unitLabel << " for logical volume '"
           << logicalVolumeName << "'" << G4endl;
    return true;
  } catch (const std::exception&) {
    G4cerr << "--> WARNING: Invalid numeric local " << fieldLabel << " field payload '"
           << assignmentPayload << "'. Expected <LogicalVolumeName>|<FieldX>|<FieldY>|<FieldZ>."
           << G4endl;
    return false;
  }
}

std::string TrimWhitespace(const std::string& value)
{
  const auto begin = value.find_first_not_of(" \t\r\n");
  if (begin == std::string::npos) {
    return "";
  }

  const auto end = value.find_last_not_of(" \t\r\n");
  return value.substr(begin, end - begin + 1);
}

std::vector<G4String> ParseTargetVolumeNames(const std::string& rawText)
{
  std::vector<G4String> targetVolumeNames;
  std::stringstream stream(rawText);
  std::string rawName;

  while (std::getline(stream, rawName, ',')) {
    const std::string trimmed = TrimWhitespace(rawName);
    if (trimmed.empty()) {
      continue;
    }

    const G4String targetVolumeName = trimmed.c_str();
    if (std::find(targetVolumeNames.begin(), targetVolumeNames.end(), targetVolumeName) !=
        targetVolumeNames.end()) {
      continue;
    }

    targetVolumeNames.push_back(targetVolumeName);
  }

  return targetVolumeNames;
}

bool ParseNumericPayload(const std::string& rawText, const G4String& fieldLabel, G4double& value)
{
  const std::string trimmed = TrimWhitespace(rawText);
  if (trimmed.empty()) {
    value = 0.0;
    return true;
  }

  try {
    value = std::stod(trimmed);
    return true;
  } catch (const std::exception&) {
    G4cerr << "--> WARNING: Invalid numeric region control payload '" << rawText
           << "' for field '" << fieldLabel << "'." << G4endl;
    return false;
  }
}

bool ParseRegionControlPayload(const G4String& assignmentPayload,
                               G4String& regionName,
                               std::vector<G4String>& targetVolumeNames,
                               G4double& productionCutMm,
                               G4double& maxStepMm,
                               G4double& maxTrackLengthMm,
                               G4double& maxTimeNs,
                               G4double& minKineticEnergyMeV,
                               G4double& minRangeMm)
{
  std::stringstream stream(assignmentPayload);
  std::string regionNameText;
  std::string targetVolumeText;
  std::string productionCutText;
  std::string maxStepText;
  std::string maxTrackLengthText;
  std::string maxTimeText;
  std::string minKineticEnergyText;
  std::string minRangeText;

  if (!std::getline(stream, regionNameText, '|') ||
      !std::getline(stream, targetVolumeText, '|') ||
      !std::getline(stream, productionCutText, '|') ||
      !std::getline(stream, maxStepText, '|') ||
      !std::getline(stream, maxTrackLengthText, '|') ||
      !std::getline(stream, maxTimeText, '|') ||
      !std::getline(stream, minKineticEnergyText, '|') ||
      !std::getline(stream, minRangeText, '|')) {
    G4cerr << "--> WARNING: Invalid region control payload '" << assignmentPayload
           << "'. Expected <RegionName>|<Volume1,Volume2>|<ProductionCutMm>|<MaxStepMm>|"
              "<MaxTrackLengthMm>|<MaxTimeNs>|<MinKineticEnergyMeV>|<MinRangeMm>."
           << G4endl;
    return false;
  }

  const std::string trimmedRegionName = TrimWhitespace(regionNameText);
  if (trimmedRegionName.empty()) {
    G4cerr << "--> WARNING: Region control payload '" << assignmentPayload
           << "' is missing a region name." << G4endl;
    return false;
  }

  regionName = trimmedRegionName.c_str();
  targetVolumeNames = ParseTargetVolumeNames(targetVolumeText);

  return ParseNumericPayload(productionCutText, "productionCutMm", productionCutMm) &&
         ParseNumericPayload(maxStepText, "maxStepMm", maxStepMm) &&
         ParseNumericPayload(maxTrackLengthText, "maxTrackLengthMm", maxTrackLengthMm) &&
         ParseNumericPayload(maxTimeText, "maxTimeNs", maxTimeNs) &&
         ParseNumericPayload(minKineticEnergyText, "minKineticEnergyMeV", minKineticEnergyMeV) &&
         ParseNumericPayload(minRangeText, "minRangeMm", minRangeMm);
}

bool HasNonZeroField(const G4ThreeVector& fieldVector)
{
  return fieldVector.mag2() > 0.0;
}

void ConfigureElectroMagneticFieldParameters(G4FieldParameters* fieldParameters)
{
  if (!fieldParameters) {
    return;
  }

  fieldParameters->SetFieldType(kElectroMagnetic);
  fieldParameters->SetEquationType(kEqElectroMagnetic);
  fieldParameters->SetStepperType(kClassicalRK4);
}

}  // namespace

DetectorConstruction::DetectorConstruction()
  : G4VUserDetectorConstruction(),
    fWorldVolume(nullptr),
    fMessenger(nullptr),
    fGlobalFieldMessenger(nullptr),
    fGlobalMagneticField(0., 0., 0.),
    fGlobalElectricField(0., 0., 0.),
    fGDMLFilename("default.gdml")
{
  fParser.SetOverlapCheck(true);
  DefineCommands();
}

DetectorConstruction::~DetectorConstruction()
{
  delete fGlobalFieldMessenger;
  delete fMessenger;
}

void DetectorConstruction::DefineCommands()
{
  fGlobalFieldMessenger = new AirPetGlobalFieldMessenger(this);

  fMessenger = new G4GenericMessenger(this, "/g4pet/detector/", "Detector control");

  fMessenger->DeclareMethod("readFile", &DetectorConstruction::SetGDMLFile)
    .SetGuidance("Read geometry from a GDML file.")
    .SetParameterName("filename", false)
    .SetStates(G4State_PreInit, G4State_Idle)
    .SetToBeBroadcasted(false);

  fMessenger->DeclareMethod("addSD", &DetectorConstruction::SetSensitiveDetector)
    .SetGuidance("Assign a sensitive detector to a logical volume.")
    .SetGuidance("Usage: /g4pet/detector/addSD <LogicalVolumeName> <SensitiveDetectorName>")
    .SetParameterName("LogicalVolumeName", false)
    .SetParameterName("SensitiveDetectorName", false)
    .SetStates(G4State_PreInit, G4State_Idle)
    .SetToBeBroadcasted(false);

  fMessenger->DeclareMethod("addLocalMagField", &DetectorConstruction::SetLocalMagneticField)
    .SetGuidance("Assign a local uniform magnetic field to a logical volume.")
    .SetGuidance("Usage: /g4pet/detector/addLocalMagField <LogicalVolumeName>|<FieldX>|<FieldY>|<FieldZ>")
    .SetParameterName("Assignment", false)
    .SetStates(G4State_PreInit, G4State_Idle)
    .SetToBeBroadcasted(false);

  fMessenger->DeclareMethod("addLocalElecField", &DetectorConstruction::SetLocalElectricField)
    .SetGuidance("Assign a local uniform electric field to a logical volume.")
    .SetGuidance("Usage: /g4pet/detector/addLocalElecField <LogicalVolumeName>|<FieldX>|<FieldY>|<FieldZ>")
    .SetParameterName("Assignment", false)
    .SetStates(G4State_PreInit, G4State_Idle)
    .SetToBeBroadcasted(false);

  fMessenger->DeclareMethod("addRegionCutsAndLimits", &DetectorConstruction::SetRegionCutsAndLimits)
    .SetGuidance("Assign region-specific production cuts and user limits to logical volumes.")
    .SetGuidance("Usage: /g4pet/detector/addRegionCutsAndLimits <RegionName>|<Volume1,Volume2>|<ProductionCutMm>|<MaxStepMm>|<MaxTrackLengthMm>|<MaxTimeNs>|<MinKineticEnergyMeV>|<MinRangeMm>")
    .SetParameterName("Assignment", false)
    .SetStates(G4State_PreInit, G4State_Idle)
    .SetToBeBroadcasted(false);
}

void DetectorConstruction::SetSensitiveDetector(G4String logicalVolumeName, G4String sdName)
{
  fSensitiveDetectorsMap[logicalVolumeName] = sdName;
  G4cout << "--> Requested sensitive detector '" << sdName << "' for logical volume '"
         << logicalVolumeName << "'" << G4endl;
}

void DetectorConstruction::SetGlobalMagneticField(G4ThreeVector value)
{
  fGlobalMagneticField = value;
  G4cout << "--> Requested global magnetic field (" << value.x() << ", " << value.y() << ", "
         << value.z() << ") tesla" << G4endl;

  if (auto* runManager = G4RunManager::GetRunManager()) {
    runManager->GeometryHasBeenModified();
  }
}

void DetectorConstruction::SetGlobalElectricField(G4ThreeVector value)
{
  fGlobalElectricField = value;
  G4cout << "--> Requested global electric field (" << value.x() << ", " << value.y() << ", "
         << value.z() << ") volt/m" << G4endl;

  if (auto* runManager = G4RunManager::GetRunManager()) {
    runManager->GeometryHasBeenModified();
  }
}

void DetectorConstruction::SetLocalMagneticField(G4String assignmentPayload)
{
  G4String logicalVolumeName;
  G4ThreeVector fieldVector;
  if (!ParseFieldAssignmentPayload(
        assignmentPayload, "magnetic", "tesla", logicalVolumeName, fieldVector)) {
    return;
  }

  fLocalMagFieldAssignments[logicalVolumeName] = fieldVector;

  if (auto* runManager = G4RunManager::GetRunManager()) {
    runManager->GeometryHasBeenModified();
  }
}

void DetectorConstruction::SetLocalElectricField(G4String assignmentPayload)
{
  G4String logicalVolumeName;
  G4ThreeVector fieldVector;
  if (!ParseFieldAssignmentPayload(
        assignmentPayload, "electric", "volt/m", logicalVolumeName, fieldVector)) {
    return;
  }

  fLocalElecFieldAssignments[logicalVolumeName] = fieldVector;

  if (auto* runManager = G4RunManager::GetRunManager()) {
    runManager->GeometryHasBeenModified();
  }
}

void DetectorConstruction::SetRegionCutsAndLimits(G4String assignmentPayload)
{
  G4String regionName;
  std::vector<G4String> targetVolumeNames;
  G4double productionCutMm = 0.0;
  G4double maxStepMm = 0.0;
  G4double maxTrackLengthMm = 0.0;
  G4double maxTimeNs = 0.0;
  G4double minKineticEnergyMeV = 0.0;
  G4double minRangeMm = 0.0;

  if (!ParseRegionControlPayload(
        assignmentPayload,
        regionName,
        targetVolumeNames,
        productionCutMm,
        maxStepMm,
        maxTrackLengthMm,
        maxTimeNs,
        minKineticEnergyMeV,
        minRangeMm)) {
    return;
  }

  RegionControlConfig& config = fRegionControlAssignments[regionName];
  config.targetVolumeNames = targetVolumeNames;
  config.productionCutMm = productionCutMm;
  config.maxStepMm = maxStepMm;
  config.maxTrackLengthMm = maxTrackLengthMm;
  config.maxTimeNs = maxTimeNs;
  config.minKineticEnergyMeV = minKineticEnergyMeV;
  config.minRangeMm = minRangeMm;

  G4cout << "--> Requested region cuts and limits for region '" << regionName << "'" << G4endl;

  if (auto* runManager = G4RunManager::GetRunManager()) {
    runManager->GeometryHasBeenModified();
  }
}

void DetectorConstruction::SetGDMLFile(G4String filename)
{
  std::ifstream ifile(filename);
  if (!ifile) {
    G4Exception("DetectorConstruction::SetGDMLFile",
                "InvalidFileName", FatalException,
                ("GDML file not found: " + filename).c_str());
    fGDMLFilename = "";
    return;
  }

  fGDMLFilename = filename;
  G4cout << "--> Geometry will be loaded from: " << fGDMLFilename << G4endl;
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  if (fGDMLFilename.empty()) {
    G4Exception("DetectorConstruction::Construct()",
                "NoGDMLFile", FatalException,
                "No GDML file specified. Use /g4pet/detector/readFile to set one.");
    return nullptr;
  }

  G4GeometryManager::GetInstance()->OpenGeometry();
  G4PhysicalVolumeStore::GetInstance()->Clean();
  G4LogicalVolumeStore::GetInstance()->Clean();
  G4SolidStore::GetInstance()->Clean();

  fParser.Read(fGDMLFilename, false);
  fWorldVolume = fParser.GetWorldVolume();

  if (!fWorldVolume) {
    G4Exception("DetectorConstruction::Construct()",
                "WorldVolumeNotFound", FatalException,
                "Could not find the World Volume in the GDML file.");
  }

  return fWorldVolume;
}

void DetectorConstruction::ConstructSDandField()
{
  G4cout << G4endl << "-------- DetectorConstruction::ConstructSDandField --------" << G4endl;

  G4SDManager* sdManager = G4SDManager::GetSDMpointer();
  G4LogicalVolumeStore* lvStore = G4LogicalVolumeStore::GetInstance();
  const bool hasGlobalField = HasNonZeroField(fGlobalMagneticField) || HasNonZeroField(fGlobalElectricField);

  bool hasLocalField = false;
  for (const auto& pair : fLocalMagFieldAssignments) {
    if (HasNonZeroField(pair.second)) {
      hasLocalField = true;
      break;
    }
  }
  if (!hasLocalField) {
    for (const auto& pair : fLocalElecFieldAssignments) {
      if (HasNonZeroField(pair.second)) {
        hasLocalField = true;
        break;
      }
    }
  }

  G4FieldBuilder* fieldBuilder = nullptr;
  if (hasGlobalField || hasLocalField) {
    fieldBuilder = G4FieldBuilder::Instance();
    fieldBuilder->SetFieldType(kElectroMagnetic);
    if (auto* globalParameters = fieldBuilder->GetFieldParameters()) {
      ConfigureElectroMagneticFieldParameters(globalParameters);
      globalParameters->SetMinimumStep(0.25 * mm);
    }

    if (hasGlobalField) {
      auto* globalField =
        new AirPetUniformElectroMagneticField(fGlobalMagneticField, fGlobalElectricField);
      fieldBuilder->SetGlobalField(globalField);
    }
  }

  for (const auto& pair : fSensitiveDetectorsMap) {
    const G4String& lvName = pair.first;
    const G4String& sdName = pair.second;

    G4LogicalVolume* logicalVolume = lvStore->GetVolume(lvName);

    if (!logicalVolume) {
      G4cerr << "--> WARNING: Logical Volume '" << lvName
             << "' not found in geometry. Cannot attach SD '" << sdName << "'." << G4endl;
      continue;
    }

    G4VSensitiveDetector* existingSD = sdManager->FindSensitiveDetector(sdName, false);

    if (existingSD) {
      G4VUserDetectorConstruction::SetSensitiveDetector(logicalVolume, existingSD);
      G4cout << "--> Attached existing sensitive detector '" << sdName
             << "' to logical volume '" << lvName << "'" << G4endl;
    } else {
      auto* airpetSD = new AirPetSensitiveDetector(sdName);
      sdManager->AddNewDetector(airpetSD);
      G4VUserDetectorConstruction::SetSensitiveDetector(logicalVolume, airpetSD);
      G4cout << "--> Created and attached new sensitive detector '" << sdName
             << "' to logical volume '" << lvName << "'" << G4endl;
    }
  }

  std::map<G4String, std::pair<G4ThreeVector, G4ThreeVector>> combinedLocalFields;
  for (const auto& pair : fLocalMagFieldAssignments) {
    combinedLocalFields[pair.first].first = pair.second;
  }
  for (const auto& pair : fLocalElecFieldAssignments) {
    combinedLocalFields[pair.first].second = pair.second;
  }

  for (const auto& pair : combinedLocalFields) {
    const G4String& lvName = pair.first;
    const G4ThreeVector& magneticField = pair.second.first;
    const G4ThreeVector& electricField = pair.second.second;

    G4LogicalVolume* logicalVolume = lvStore->GetVolume(lvName);

    if (!logicalVolume) {
      G4cerr << "--> WARNING: Logical Volume '" << lvName
             << "' not found in geometry. Cannot attach local field." << G4endl;
      continue;
    }

    if (fieldBuilder) {
      if (auto* localParameters = fieldBuilder->GetFieldParameters(lvName)) {
        ConfigureElectroMagneticFieldParameters(localParameters);
        localParameters->SetMinimumStep(0.25 * mm);
      } else {
        auto* createdParameters = fieldBuilder->CreateFieldParameters(lvName);
        if (createdParameters) {
          ConfigureElectroMagneticFieldParameters(createdParameters);
          createdParameters->SetMinimumStep(0.25 * mm);
        }
      }
      auto* localField = new AirPetUniformElectroMagneticField(magneticField, electricField);
      fieldBuilder->SetLocalField(localField, logicalVolume);

      G4cout << "--> Attached local field (" << magneticField.x() << ", " << magneticField.y()
             << ", " << magneticField.z() << ") tesla and (" << electricField.x() << ", "
             << electricField.y() << ", " << electricField.z() << ") volt/m to logical volume '"
             << lvName << "'" << G4endl;
    }
  }

  for (const auto& pair : fRegionControlAssignments) {
    const G4String& regionName = pair.first;
    const RegionControlConfig& config = pair.second;

    if (config.targetVolumeNames.empty()) {
      G4cerr << "--> WARNING: Region control assignment for region '" << regionName
             << "' does not reference any logical volumes." << G4endl;
      continue;
    }

    G4Region* region = G4RegionStore::GetInstance()->GetRegion(regionName, false);
    if (!region) {
      region = new G4Region(regionName);
    }

    for (const auto& lvName : config.targetVolumeNames) {
      G4LogicalVolume* logicalVolume = lvStore->GetVolume(lvName);

      if (!logicalVolume) {
        G4cerr << "--> WARNING: Logical Volume '" << lvName
               << "' not found in geometry. Cannot attach region control '" << regionName
               << "'." << G4endl;
        continue;
      }

      region->AddRootLogicalVolume(logicalVolume);
      G4cout << "--> Attached logical volume '" << lvName
             << "' to region control '" << regionName << "'" << G4endl;
    }

    if (config.productionCutMm > 0.0) {
      auto* productionCuts = new G4ProductionCuts();
      productionCuts->SetProductionCut(config.productionCutMm * mm);
      region->SetProductionCuts(productionCuts);
      G4cout << "--> Requested region production cut " << config.productionCutMm
             << " mm for region '" << regionName << "'" << G4endl;
    }

    const bool hasUserLimits = config.maxStepMm > 0.0 || config.maxTrackLengthMm > 0.0 ||
                               config.maxTimeNs > 0.0 || config.minKineticEnergyMeV > 0.0 ||
                               config.minRangeMm > 0.0;
    if (hasUserLimits) {
      auto* userLimits = new G4UserLimits();
      if (config.maxStepMm > 0.0) {
        userLimits->SetMaxAllowedStep(config.maxStepMm * mm);
      }
      if (config.maxTrackLengthMm > 0.0) {
        userLimits->SetUserMaxTrackLength(config.maxTrackLengthMm * mm);
      }
      if (config.maxTimeNs > 0.0) {
        userLimits->SetUserMaxTime(config.maxTimeNs * ns);
      }
      if (config.minKineticEnergyMeV > 0.0) {
        userLimits->SetUserMinEkine(config.minKineticEnergyMeV * MeV);
      }
      if (config.minRangeMm > 0.0) {
        userLimits->SetUserMinRange(config.minRangeMm * mm);
      }
      region->SetUserLimits(userLimits);
      G4cout << "--> Requested region user limits for region '" << regionName << "'" << G4endl;
    }
  }

  if (fieldBuilder) {
    fieldBuilder->ConstructFieldSetup();
  }
}
