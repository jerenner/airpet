#include "DetectorConstruction.hh"
#include "AirPetSensitiveDetector.hh"

#include "G4RunManager.hh"
#include "G4GenericMessenger.hh"
#include "G4UIdirectory.hh"
#include "G4UIcommand.hh"
#include "G4UIparameter.hh"
#include "G4UIcmdWithAString.hh"
#include "G4SDManager.hh"
#include "G4LogicalVolumeStore.hh"
#include "G4SolidStore.hh"
#include "G4PhysicalVolumeStore.hh"
#include "G4GeometryManager.hh"

DetectorConstruction::DetectorConstruction()
 : G4VUserDetectorConstruction(),
   fWorldVolume(nullptr),
   fMessenger(nullptr),
   fGDMLFilename("default.gdml") // A default name
{
  // The G4GDMLParser can be configured to check for overlaps
  fParser.SetOverlapCheck(true);
  DefineCommands();
}

DetectorConstruction::~DetectorConstruction()
{
  delete fMessenger;
}

void DetectorConstruction::DefineCommands()
{

  // The G4GenericMessenger ties UI commands to methods of this class.
  // The 'this' pointer is passed here.
  fMessenger = new G4GenericMessenger(this, "/g4pet/detector/", "Detector control");

  // Command to read a GDML file
  fMessenger->DeclareMethod("readFile", &DetectorConstruction::SetGDMLFile)
      .SetGuidance("Read geometry from a GDML file.")
      .SetParameterName("filename", false) // The name for the one and only parameter
      .SetStates(G4State_PreInit, G4State_Idle)
      .SetToBeBroadcasted(false);

  // Command to add a Sensitive Detector to a Logical Volume
  fMessenger->DeclareMethod("addSD", &DetectorConstruction::SetSensitiveDetector)
      .SetGuidance("Assign a sensitive detector to a logical volume.")
      .SetGuidance("Usage: /g4pet/detector/addSD <LogicalVolumeName> <SensitiveDetectorName>")
      .SetParameterName("LogicalVolumeName",     /*omittable=*/false)
      .SetParameterName("SensitiveDetectorName", /*omittable=*/false)
      .SetStates(G4State_PreInit, G4State_Idle)
      .SetToBeBroadcasted(false);
}

// This method is defined for the messenger (takes G4Strings)
void DetectorConstruction::SetSensitiveDetector(G4String logicalVolumeName, G4String sdName)
{
  fSensitiveDetectorsMap[logicalVolumeName] = sdName;
  G4cout << "--> Requested sensitive detector '" << sdName
         << "' for logical volume '" << logicalVolumeName << "'" << G4endl;

  // Tell the RunManager that the detector setup has changed and needs to be rebuilt.
  // This will ensure ConstructSDandField() is called again before the next run.
  //G4RunManager::GetRunManager()->ReinitializeGeometry();
}

void DetectorConstruction::SetGDMLFile(G4String filename)
{
  // Check if the file exists before storing the name
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

  // Inform the RunManager that the geometry needs to be rebuilt
  //G4RunManager::GetRunManager()->ReinitializeGeometry();
  //G4cout << "--> Geometry will be loaded from: " << fGDMLFilename << G4endl;
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
  if (fGDMLFilename.empty()) {
    G4Exception("DetectorConstruction::Construct()",
                "NoGDMLFile", FatalException,
                "No GDML file specified. Use /g4pet/detector/readFile to set one.");
    return nullptr;
  }

  // Clear any previously loaded geometry
  G4GeometryManager::GetInstance()->OpenGeometry();
  G4PhysicalVolumeStore::GetInstance()->Clean();
  G4LogicalVolumeStore::GetInstance()->Clean();
  G4SolidStore::GetInstance()->Clean();

  // Parse the GDML file
  // The parser will create all materials, solids, and logical/physical volumes.
  fParser.Read(fGDMLFilename, false); // false = do not validate schema

  // Get the pointer to the world volume
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
  
  // Iterate over all the SD attachment requests made via the messenger
  //G4cout << "--> Sensitve det map contains " << fSensitiveDetectorsMap.size() << " detector" << G4endl;
  for (const auto& pair : fSensitiveDetectorsMap) {
    const G4String& lvName = pair.first;
    const G4String& sdName = pair.second;

    G4LogicalVolume* logicalVolume = lvStore->GetVolume(lvName);

    if (!logicalVolume) {
      G4cerr << "--> WARNING: Logical Volume '" << lvName
             << "' not found in geometry. Cannot attach SD '"
             << sdName << "'." << G4endl;
      continue;
    }

    // Check if the SD already exists
    G4VSensitiveDetector* existingSD = sdManager->FindSensitiveDetector(sdName, false); // false = don't warn if not found

    if (existingSD) {
      // Use the base class's method to attach the SD
      G4VUserDetectorConstruction::SetSensitiveDetector(logicalVolume, existingSD);
      G4cout << "--> Attached existing sensitive detector '" << sdName
             << "' to logical volume '" << lvName << "'" << G4endl;
    }
    else {
      // If it doesn't exist, create a new instance of our generic SD
      auto* airpetSD = new AirPetSensitiveDetector(sdName);
      sdManager->AddNewDetector(airpetSD);
      // Use the base class's method to attach the SD
      G4VUserDetectorConstruction::SetSensitiveDetector(logicalVolume, airpetSD);
      G4cout << "--> Created and attached new sensitive detector '" << sdName
             << "' to logical volume '" << lvName << "'" << G4endl;
    }
  }
}