#include "RunAction.hh"
#include "EventAction.hh" // We need the full definition here

#include "G4AnalysisManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"

#include "G4UIcmdWithADoubleAndUnit.hh"
#include "G4UIcommand.hh"
#include "G4UIdirectory.hh"
#include "G4UIparameter.hh"

RunAction::RunAction()
    : G4UserRunAction(), fSaveParticles(false), fSaveHits(true),
      fHitEnergyThreshold(0.0) {

  // Set up the G4AnalysisManager singleton
  auto analysisManager = G4AnalysisManager::Instance();
  analysisManager->SetCompressionLevel(1);

  // --- Define the UI commands ---
  fG4petDir = new G4UIdirectory("/g4pet/");
  fG4petDir->SetGuidance("UI commands specific to the virtual-pet application");

  fRunDir = new G4UIdirectory("/g4pet/run/");
  fRunDir->SetGuidance("Run-level control");

  // Command to control saving tracks
  fSaveParticlesCmd = new G4UIcommand("/g4pet/run/saveParticles", this);
  fSaveParticlesCmd->SetGuidance("Enable/disable saving the Tracks n-tuple.");
  fSaveParticlesCmd->SetParameter(
      new G4UIparameter("value", 'b', true)); // 'b' for boolean
  fSaveParticlesCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Command to control saving hits
  fSaveHitsCmd = new G4UIcommand("/g4pet/run/saveHits", this);
  fSaveHitsCmd->SetGuidance("Enable/disable saving the Hits n-tuple.");
  fSaveHitsCmd->SetParameter(new G4UIparameter("value", 'b', true));
  fSaveHitsCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Command to set hit energy threshold
  fHitEnergyThresholdCmd =
      new G4UIcmdWithADoubleAndUnit("/g4pet/run/hitEnergyThreshold", this);
  fHitEnergyThresholdCmd->SetGuidance(
      "Set the energy threshold for saving hits.");
  fHitEnergyThresholdCmd->SetParameterName("energy", true);
  fHitEnergyThresholdCmd->SetDefaultValue(0.0);
  fHitEnergyThresholdCmd->SetUnitCategory("Energy");
  fHitEnergyThresholdCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

RunAction::~RunAction() {
  // The G4AnalysisManager is a singleton and is deleted by Geant4,
  // so we don't delete it here.

  // Commenting out all deletions to prevent segfault on exit
  // delete fSaveParticlesCmd;
  // delete fSaveHitsCmd;
  // delete fHitEnergyThresholdCmd;
  // delete fRunDir;
  // delete fG4petDir; // Avoid double deletion if shared/conflicting with
  // EventAction
}

void RunAction::SetNewValue(G4UIcommand *command, G4String newValue) {
  if (command == fSaveParticlesCmd) {
    fSaveParticles = G4UIcommand::ConvertToBool(newValue);
  } else if (command == fSaveHitsCmd) {
    fSaveHits = G4UIcommand::ConvertToBool(newValue);
  } else if (command == fHitEnergyThresholdCmd) {
    fHitEnergyThreshold = fHitEnergyThresholdCmd->GetNewDoubleValue(newValue);
  }
}

void RunAction::BeginOfRunAction(const G4Run * /*aRun*/) {
  // Get the analysis manager
  auto analysisManager = G4AnalysisManager::Instance();

  // Open an output file. The filename can be set with a macro
  // command `/analysis/setFileName new_name.hdf5`
  analysisManager->OpenFile();

  if (fSaveParticles) {

    // --- Create N-tuple for Particle Tracks (ID 0) ---
    // This n-tuple will store detailed information for each particle
    // trajectory.
    analysisManager->CreateNtuple("Tracks", "Particle Trajectories");
    analysisManager->CreateNtupleIColumn("EventID");        // 0
    analysisManager->CreateNtupleSColumn("ParticleName");   // 1
    analysisManager->CreateNtupleIColumn("TrackID");        // 2
    analysisManager->CreateNtupleIColumn("ParentID");       // 3
    analysisManager->CreateNtupleDColumn("Mass");           // 4 (in MeV)
    analysisManager->CreateNtupleDColumn("InitialPosX");    // 5 (in mm)
    analysisManager->CreateNtupleDColumn("InitialPosY");    // 6 (in mm)
    analysisManager->CreateNtupleDColumn("InitialPosZ");    // 7 (in mm)
    analysisManager->CreateNtupleDColumn("InitialTime");    // 8 (in ns)
    analysisManager->CreateNtupleDColumn("FinalPosX");      // 9 (in mm)
    analysisManager->CreateNtupleDColumn("FinalPosY");      // 10 (in mm)
    analysisManager->CreateNtupleDColumn("FinalPosZ");      // 11 (in mm)
    analysisManager->CreateNtupleDColumn("FinalTime");      // 12 (in ns)
    analysisManager->CreateNtupleDColumn("InitialMomX");    // 13 (in MeV/c)
    analysisManager->CreateNtupleDColumn("InitialMomY");    // 14 (in MeV/c)
    analysisManager->CreateNtupleDColumn("InitialMomZ");    // 15 (in MeV/c)
    analysisManager->CreateNtupleDColumn("FinalMomX");      // 16 (in MeV/c)
    analysisManager->CreateNtupleDColumn("FinalMomY");      // 17 (in MeV/c)
    analysisManager->CreateNtupleDColumn("FinalMomZ");      // 18 (in MeV/c)
    analysisManager->CreateNtupleSColumn("InitialVolume");  // 19
    analysisManager->CreateNtupleSColumn("FinalVolume");    // 20
    analysisManager->CreateNtupleSColumn("CreatorProcess"); // 21
    analysisManager->FinishNtuple(0); // Finalize the first n-tuple
  }

  if (fSaveHits) {

    // If we're also saving the particles, the ntuple ID will be 1.
    // Otherwise, it will be 0.
    G4int hits_ntuple_ID = 0;
    if (fSaveParticles) {
      hits_ntuple_ID = 1;
    }

    // --- Create N-tuple for Sensitive Detector Hits (ID 1) ---
    // This n-tuple stores information from every hit in any sensitive detector.
    analysisManager->CreateNtuple("Hits", "Sensitive Detector Hits");
    analysisManager->CreateNtupleIColumn("EventID"); // 0
    // analysisManager->CreateNtupleSColumn("DetectorName"); // Removed for disk
    // space analysisManager->CreateNtupleSColumn("PhysicalVolumeName"); //
    // Removed analysisManager->CreateNtupleSColumn("VolumeName");   // Removed
    analysisManager->CreateNtupleIColumn("CopyNo");       // 1 (was 4)
    analysisManager->CreateNtupleSColumn("ParticleName"); // 2 (was 5)
    analysisManager->CreateNtupleIColumn("TrackID");      // 3 (was 6)
    analysisManager->CreateNtupleIColumn("ParentID");     // 4 (was 7)
    analysisManager->CreateNtupleDColumn("Edep");         // 5 (was 8) (in MeV)
    analysisManager->CreateNtupleDColumn("PosX");         // 6 (was 9) (in mm)
    analysisManager->CreateNtupleDColumn("PosY");         // 7 (was 10) (in mm)
    analysisManager->CreateNtupleDColumn("PosZ");         // 8 (was 11) (in mm)
    analysisManager->CreateNtupleDColumn("Time");         // 9 (was 12) (in ns)
    analysisManager->FinishNtuple(
        fSaveParticles); // Finalize the second n-tuple
  }
}

void RunAction::EndOfRunAction(const G4Run * /*aRun*/) {
  auto analysisManager = G4AnalysisManager::Instance();

  // Write the n-tuples to the file.
  // In a multi-threaded run, this method is called only by the master thread
  // after all worker threads have finished, and the manager handles merging.
  analysisManager->Write();

  // Close the file.
  analysisManager->CloseFile();
}