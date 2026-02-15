#include "G4RunManagerFactory.hh"
#include "G4SteppingVerbose.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"

#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"

// Physics Lists
#include "G4PhysListFactory.hh"
#include "G4VModularPhysicsList.hh"
#include "G4OpticalPhysics.hh"

// Main program
int main(int argc, char **argv) {
  // Detect interactive mode (if no macro file is specified)
  G4UIExecutive *ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  // Use recommended G4SteppingVerbose
  G4int precision = 4;
  G4SteppingVerbose::UseBestUnit(precision);

  // Construct the default run manager
  auto *runManager =
      G4RunManagerFactory::CreateRunManager(G4RunManagerType::Serial);

  // Set mandatory initialization classes
  // 1. DetectorConstruction
  auto *detConstruction = new DetectorConstruction();
  runManager->SetUserInitialization(detConstruction);

  // 2. Physics list
  // We use a factory to allow dynamic selection via environment variables
  G4PhysListFactory factory;
  G4String physListName = "FTFP_BERT"; // Default
  
  const char* envPhysList = std::getenv("G4PHYSICSLIST");
  if (envPhysList) {
    physListName = envPhysList;
  }
  
  G4VModularPhysicsList* physicsList = factory.GetReferencePhysList(physListName);
  if (!physicsList) {
    G4cerr << "!!! ERROR: Physics list '" << physListName << "' not found. Falling back to FTFP_BERT." << G4endl;
    physicsList = factory.GetReferencePhysList("FTFP_BERT");
  }

  // Check for Optical Physics
  const char* envOptical = std::getenv("G4OPTICALPHYSICS");
  if (envOptical && (std::string(envOptical) == "on" || std::string(envOptical) == "true")) {
    G4cout << "--> Registering G4OpticalPhysics..." << G4endl;
    physicsList->RegisterPhysics(new G4OpticalPhysics());
  }

  runManager->SetUserInitialization(physicsList);

  // 3. User action initialization
  runManager->SetUserInitialization(new ActionInitialization());

  // Initialize visualization
  G4VisManager *visManager = nullptr;

  // Get the pointer to the User Interface manager
  G4UImanager *UImanager = G4UImanager::GetUIpointer();

  if (!ui) {
    // Batch mode: execute the macro file provided as the first argument
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    UImanager->ApplyCommand(command + fileName);
  } else {
    // --- INTERACTIVE MODE ---
    // Initialize visualization
    visManager = new G4VisExecutive;
    visManager->Initialize();
    // Load default visualization and GUI macros
    UImanager->ApplyCommand("/control/execute init_vis.mac");
    if (ui->IsGUI()) {
      UImanager->ApplyCommand("/control/execute gui.mac");
    }
    ui->SessionStart();
    delete ui;
  }

  // Job termination
  delete visManager;
  delete runManager;

  return 0;
}