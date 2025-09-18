#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"
#include "G4SteppingVerbose.hh"

#include "DetectorConstruction.hh"
#include "ActionInitialization.hh"
#include "FTFP_BERT.hh" // A good, standard physics list

// Custom User Classes
#include "DetectorConstruction.hh"
#include "ActionInitialization.hh"

// Main program
int main(int argc, char** argv)
{
  // Detect interactive mode (if no macro file is specified)
  G4UIExecutive* ui = nullptr;
  if (argc == 1) {
    ui = new G4UIExecutive(argc, argv);
  }

  // Use recommended G4SteppingVerbose
  // This can be controlled later via macros if needed
  G4int precision = 4;
  G4SteppingVerbose::UseBestUnit(precision);

  // Construct the default run manager
  // Using G4RunManagerFactory allows for easy switching to multi-threading
  auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);
  // Example of setting a default number of threads, can be overridden by macro
  // runManager->SetNumberOfThreads(4);

  // Set mandatory initialization classes
  //
  // 1. DetectorConstruction
  // This class will be responsible for reading the GDML file.
  // We pass it a default filename which will be overridden by a macro command.
  auto* detConstruction = new DetectorConstruction();
  runManager->SetUserInitialization(detConstruction);

  // 2. Physics list
  // FTFP_BERT is a good general-purpose physics list.
  // This can also be made configurable later if desired.
  auto* physicsList = new FTFP_BERT;
  runManager->SetUserInitialization(physicsList);

  // 3. User action initialization
  // This class will set up all the user actions (generator, run, event, etc.)
  runManager->SetUserInitialization(new ActionInitialization());

  // Initialize visualization
  auto* visManager = new G4VisExecutive;

  // Get the pointer to the User Interface manager
  G4UImanager* UImanager = G4UImanager::GetUIpointer();

  if (!ui) {
    // Batch mode: execute the macro file provided as the first argument
    G4String command = "/control/execute ";
    G4String fileName = argv[1];
    UImanager->ApplyCommand(command + fileName);
  }
  else {
    // --- INTERACTIVE MODE ---
    // Initialize visualization
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