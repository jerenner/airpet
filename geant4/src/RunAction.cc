#include "RunAction.hh"
#include "EventAction.hh" // We need the full definition here

#include "G4RunManager.hh"
#include "G4Run.hh"
#include "G4AnalysisManager.hh"
#include "G4SystemOfUnits.hh"

RunAction::RunAction(EventAction* eventAction)
 : G4UserRunAction(),
   fEventAction(eventAction)
{
  // Get the G4AnalysisManager singleton
  auto analysisManager = G4AnalysisManager::Instance();
  analysisManager->SetVerboseLevel(1);

  // Set the default filename. This can be overridden by a macro.
  analysisManager->SetFileName("virtual_pet_sim.hdf5");

  // Enable n-tuple merging for multi-threaded runs
  analysisManager->SetNtupleMerging(true);

  // --- Create N-tuple for Particle Tracks (ID 0) ---
  // This n-tuple will store detailed information for each particle trajectory.
  analysisManager->CreateNtuple("Tracks", "Particle Trajectories");
  analysisManager->CreateNtupleIColumn("EventID");      // 0
  analysisManager->CreateNtupleSColumn("ParticleName"); // 1
  analysisManager->CreateNtupleIColumn("TrackID");      // 2
  analysisManager->CreateNtupleIColumn("ParentID");     // 3
  analysisManager->CreateNtupleDColumn("Mass");         // 4 (in MeV)
  analysisManager->CreateNtupleDColumn("InitialPosX");  // 5 (in mm)
  analysisManager->CreateNtupleDColumn("InitialPosY");  // 6 (in mm)
  analysisManager->CreateNtupleDColumn("InitialPosZ");  // 7 (in mm)
  analysisManager->CreateNtupleDColumn("InitialTime");  // 8 (in ns)
  analysisManager->CreateNtupleDColumn("FinalPosX");    // 9 (in mm)
  analysisManager->CreateNtupleDColumn("FinalPosY");    // 10 (in mm)
  analysisManager->CreateNtupleDColumn("FinalPosZ");    // 11 (in mm)
  analysisManager->CreateNtupleDColumn("FinalTime");    // 12 (in ns)
  analysisManager->CreateNtupleDColumn("InitialMomX");  // 13 (in MeV/c)
  analysisManager->CreateNtupleDColumn("InitialMomY");  // 14 (in MeV/c)
  analysisManager->CreateNtupleDColumn("InitialMomZ");  // 15 (in MeV/c)
  analysisManager->CreateNtupleDColumn("FinalMomX");    // 16 (in MeV/c)
  analysisManager->CreateNtupleDColumn("FinalMomY");    // 17 (in MeV/c)
  analysisManager->CreateNtupleDColumn("FinalMomZ");    // 18 (in MeV/c)
  analysisManager->CreateNtupleSColumn("InitialVolume"); // 19
  analysisManager->CreateNtupleSColumn("FinalVolume");   // 20
  analysisManager->CreateNtupleSColumn("CreatorProcess"); // 21
  analysisManager->FinishNtuple(0); // Finalize the first n-tuple

  // --- Create N-tuple for Sensitive Detector Hits (ID 1) ---
  // This n-tuple stores information from every hit in any sensitive detector.
  analysisManager->CreateNtuple("Hits", "Sensitive Detector Hits");
  analysisManager->CreateNtupleIColumn("EventID");        // 0
  analysisManager->CreateNtupleSColumn("DetectorName");   // 1 (Name of the SD)
  analysisManager->CreateNtupleSColumn("VolumeName");     // 2 (Name of the LV)
  analysisManager->CreateNtupleIColumn("CopyNo");         // 3
  analysisManager->CreateNtupleSColumn("ParticleName");   // 4
  analysisManager->CreateNtupleIColumn("TrackID");        // 5
  analysisManager->CreateNtupleIColumn("ParentID");       // 6
  analysisManager->CreateNtupleDColumn("Edep");           // 7 (in MeV)
  analysisManager->CreateNtupleDColumn("PosX");           // 8 (in mm)
  analysisManager->CreateNtupleDColumn("PosY");           // 9 (in mm)
  analysisManager->CreateNtupleDColumn("PosZ");           // 10 (in mm)
  analysisManager->CreateNtupleDColumn("Time");           // 11 (in ns)
  analysisManager->FinishNtuple(1); // Finalize the second n-tuple
}

RunAction::~RunAction()
{
  // The G4AnalysisManager is a singleton and is deleted by Geant4,
  // so we don't delete it here.
}

void RunAction::BeginOfRunAction(const G4Run* /*aRun*/)
{
  // Get the analysis manager
  auto analysisManager = G4AnalysisManager::Instance();

  // Open an output file. The filename has been set in the constructor,
  // but can be changed with a macro command `/analysis/setFileName new_name.hdf5`
  analysisManager->OpenFile();
}

void RunAction::EndOfRunAction(const G4Run* /*aRun*/)
{
  auto analysisManager = G4AnalysisManager::Instance();

  // Write the n-tuples to the file.
  // In a multi-threaded run, this method is called only by the master thread
  // after all worker threads have finished, and the manager handles merging.
  analysisManager->Write();

  // Close the file.
  analysisManager->CloseFile();
}