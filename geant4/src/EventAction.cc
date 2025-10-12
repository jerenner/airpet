#include "EventAction.hh"
#include "RunAction.hh" // To access RunAction methods if needed
#include "AirPetHit.hh"
#include "AirPetTrajectory.hh" // We will create this next
#include "TrackingAction.hh"

#include "G4Event.hh"
#include "G4RunManager.hh"
#include "G4SDManager.hh"
#include "G4HCofThisEvent.hh"
#include "G4AnalysisManager.hh"
#include "G4TrajectoryContainer.hh"
#include "G4ios.hh"
#include "G4HCtable.hh"

// --- Includes for the messenger ---
#include "G4UIdirectory.hh"
#include "G4UIcommand.hh"
#include "G4UIparameter.hh"
#include "G4Tokenizer.hh"

#include <fstream>

EventAction::EventAction()
 : G4UserEventAction(),
   fTrackOutputDir("."),
   fStartEventToTrack(0),
   fEndEventToTrack(0)
{
  // Initialize the vector with an invalid ID
  fHitsCollectionIDs.push_back(-1);

  // --- Define the UI commands ---
  fG4petDir = new G4UIdirectory("/g4pet/");
  fG4petDir->SetGuidance("UI commands specific to the virtual-pet application");

  fEventDir = new G4UIdirectory("/g4pet/event/");
  fEventDir->SetGuidance("Event-level control");

  // Command to set output directory
  fTrackOutputDirCmd = new G4UIcommand("/g4pet/event/printTracksToDir", this);
  fTrackOutputDirCmd->SetGuidance("Set the output directory for trajectory files.");
  fTrackOutputDirCmd->SetParameter(new G4UIparameter("dir", 's', false)); // 's' for string
  fTrackOutputDirCmd->AvailableForStates(G4State_PreInit, G4State_Idle);

  // Command for track visualization event range
  fSetTrackEventRangeCmd = new G4UIcommand("/g4pet/event/setTrackEventRange", this);
  fSetTrackEventRangeCmd->SetGuidance("Set the range of event IDs for which to save tracks.");
  fSetTrackEventRangeCmd->SetGuidance("Usage: /g4pet/event/setTrackEventRange startEventID endEventID");

  G4UIparameter* startParam = new G4UIparameter("startEvent", 'i', false);
  startParam->SetGuidance("Starting event ID");
  fSetTrackEventRangeCmd->SetParameter(startParam);

  G4UIparameter* endParam = new G4UIparameter("endEvent", 'i', false);
  endParam->SetGuidance("Ending event ID");
  fSetTrackEventRangeCmd->SetParameter(endParam);
  fSetTrackEventRangeCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

EventAction::~EventAction()
{
  delete fTrackOutputDirCmd;
  delete fSetTrackEventRangeCmd;
  delete fEventDir;
  delete fG4petDir;
}

void EventAction::SetNewValue(G4UIcommand* command, G4String newValue)
{
  if (command == fTrackOutputDirCmd) {
    fTrackOutputDir = newValue;
  }
  else if (command == fSetTrackEventRangeCmd) {
    G4Tokenizer next(newValue);
    fStartEventToTrack = StoI(next());
    fEndEventToTrack = StoI(next());
  }
}

void EventAction::SetTrackEventRange(G4int start, G4int end)
{
    fStartEventToTrack = start;
    fEndEventToTrack = end;
    G4cout << "Track saving range set to events " << start << " through " << end << G4endl;
}

void EventAction::BeginOfEventAction(const G4Event* /*event*/)
{
  // You can add per-event initialization here if needed.
  // For example, resetting per-event counters.
}

void EventAction::EndOfEventAction(const G4Event* event)
{
  // Get the G4AnalysisManager instance
  auto analysisManager = G4AnalysisManager::Instance();

  // --- Get the RunAction to check flags on ntuples ---
  auto runAction = static_cast<const RunAction*>(G4RunManager::GetRunManager()->GetUserRunAction());
  if (!runAction) {
      G4Exception("EventAction::EndOfEventAction()", "Event002", FatalException, "RunAction not found.");
      return;
  }

  // --- Hits Collection Processing ---
  if (runAction->GetSaveHits()) {

    // If we're also saving the particles, the ntuple ID will be 1.
    // Otherwise, it will be 0.
    G4int hits_ntuple_ID = 0;
    if(runAction->GetSaveParticles()) { 
      hits_ntuple_ID = 1;
    }

    // On the first event, get the collection IDs for all registered SDs.
    if (fHitsCollectionIDs[0] == -1) {
      fHitsCollectionIDs.clear();
      G4SDManager* sdManager = G4SDManager::GetSDMpointer();
      G4HCtable* hcTable = sdManager->GetHCtable();

      // Loop through all entries in the hits collection table
      for (G4int i = 0; i < hcTable->entries(); ++i) {
        // Get the collection name for the i-th entry
        G4String collectionName = hcTable->GetHCname(i);
        // Get the unique integer ID for that collection name
        G4int cID = sdManager->GetCollectionID(collectionName);
        if (cID >= 0) {
          fHitsCollectionIDs.push_back(cID);
        }
      }
    }

    G4HCofThisEvent* hce = event->GetHCofThisEvent();
    if (!hce) {
        G4Exception("EventAction::EndOfEventAction()",
                    "Event001", JustWarning,
                    "No HCofThisEvent found.");
        return;
    }

    // Loop over all registered hits collections
    for (G4int cID : fHitsCollectionIDs) {
      auto hitsCollection = static_cast<AirPetHitsCollection*>(hce->GetHC(cID));
      if (hitsCollection) {
        for (size_t i = 0; i < hitsCollection->GetSize(); ++i) {
          auto hit = static_cast<AirPetHit*>(hitsCollection->GetHit(i));

          // Fill the "Hits" n-tuple
          analysisManager->FillNtupleIColumn(hits_ntuple_ID, 0, event->GetEventID());
          analysisManager->FillNtupleSColumn(hits_ntuple_ID, 1, hitsCollection->GetSDname());
          analysisManager->FillNtupleSColumn(hits_ntuple_ID, 2, hit->GetPhysicalVolumeName());
          analysisManager->FillNtupleSColumn(hits_ntuple_ID, 3, hit->GetVolumeName());
          analysisManager->FillNtupleIColumn(hits_ntuple_ID, 4, hit->GetCopyNo());
          analysisManager->FillNtupleSColumn(hits_ntuple_ID, 5, hit->GetParticleName());
          analysisManager->FillNtupleIColumn(hits_ntuple_ID, 6, hit->GetTrackID());
          analysisManager->FillNtupleIColumn(hits_ntuple_ID, 7, hit->GetParentID());
          analysisManager->FillNtupleDColumn(hits_ntuple_ID, 8, hit->GetEdep());
          analysisManager->FillNtupleDColumn(hits_ntuple_ID, 9, hit->GetPosition().x());
          analysisManager->FillNtupleDColumn(hits_ntuple_ID, 10, hit->GetPosition().y());
          analysisManager->FillNtupleDColumn(hits_ntuple_ID, 11, hit->GetPosition().z());
          analysisManager->FillNtupleDColumn(hits_ntuple_ID, 12, hit->GetTime());
          analysisManager->AddNtupleRow(hits_ntuple_ID);

        }
      }
    }

  }

  // --- Trajectory Processing ---
  if (runAction->GetSaveParticles()) {
    G4TrajectoryContainer* trajectoryContainer = event->GetTrajectoryContainer();
    if (trajectoryContainer) {
      for (size_t i = 0; i < trajectoryContainer->size(); ++i) {
        auto traj = dynamic_cast<AirPetTrajectory*>((*trajectoryContainer)[i]);
        if (traj) {
          // Fill the "Tracks" n-tuple (ID 0)
          analysisManager->FillNtupleIColumn(0, 0, event->GetEventID());
          analysisManager->FillNtupleSColumn(0, 1, traj->GetParticleName());
          analysisManager->FillNtupleIColumn(0, 2, traj->GetTrackID());
          analysisManager->FillNtupleIColumn(0, 3, traj->GetParentID());
          analysisManager->FillNtupleDColumn(0, 4, traj->GetMass());
          analysisManager->FillNtupleDColumn(0, 5, traj->GetInitialPosition().x());
          analysisManager->FillNtupleDColumn(0, 6, traj->GetInitialPosition().y());
          analysisManager->FillNtupleDColumn(0, 7, traj->GetInitialPosition().z());
          analysisManager->FillNtupleDColumn(0, 8, traj->GetInitialTime());
          analysisManager->FillNtupleDColumn(0, 9, traj->GetFinalPosition().x());
          analysisManager->FillNtupleDColumn(0, 10, traj->GetFinalPosition().y());
          analysisManager->FillNtupleDColumn(0, 11, traj->GetFinalPosition().z());
          analysisManager->FillNtupleDColumn(0, 12, traj->GetFinalTime());
          analysisManager->FillNtupleDColumn(0, 13, traj->GetInitialMomentum().x());
          analysisManager->FillNtupleDColumn(0, 14, traj->GetInitialMomentum().y());
          analysisManager->FillNtupleDColumn(0, 15, traj->GetInitialMomentum().z());
          analysisManager->FillNtupleDColumn(0, 16, traj->GetFinalMomentum().x());
          analysisManager->FillNtupleDColumn(0, 17, traj->GetFinalMomentum().y());
          analysisManager->FillNtupleDColumn(0, 18, traj->GetFinalMomentum().z());
          analysisManager->FillNtupleSColumn(0, 19, traj->GetInitialVolume());
          analysisManager->FillNtupleSColumn(0, 20, traj->GetFinalVolume());
          analysisManager->FillNtupleSColumn(0, 21, traj->GetCreatorProcess());
          analysisManager->AddNtupleRow(0);
        }
      }
    }
  }

  // --- Trajectory File Output ---
  G4int eventID = event->GetEventID();
  if (eventID >= fStartEventToTrack && eventID <= fEndEventToTrack) {
    WriteTracksToFile(event);
  }
}

void EventAction::WriteTracksToFile(const G4Event* event)
{
    G4TrajectoryContainer* trajectoryContainer = event->GetTrajectoryContainer();
    if (!trajectoryContainer) return;

    // Create a filename for this event's tracks
    std::ostringstream filename;
    
    // Prepend the directory path to the filename
    filename << fTrackOutputDir << "/event_" << std::setw(4) << std::setfill('0') << event->GetEventID() << "_tracks.txt";

    std::ofstream outFile(filename.str());
    if (!outFile.is_open()) {
        G4cerr << "ERROR: Could not open track output file: " << filename.str() << G4endl;
        return;
    }

    // Write a simple header
    outFile << "# EventID ParticleName TrackID ParentID PDGCode\n";

    // Loop over all trajectories in the event
    for (size_t i = 0; i < trajectoryContainer->size(); ++i) {
        auto traj = dynamic_cast<AirPetTrajectory*>((*trajectoryContainer)[i]);
        if (traj) {
            outFile << "T " << event->GetEventID() << " "
                    << traj->GetParticleName() << " "
                    << traj->GetTrackID() << " "
                    << traj->GetParentID() << " "
                    << traj->GetPDGEncoding() << "\n";

            // Loop over all points in this trajectory
            for (int j = 0; j < traj->GetPointEntries(); ++j) {
                G4VTrajectoryPoint* point = traj->GetPoint(j);
                const G4ThreeVector& pos = point->GetPosition();
                outFile << pos.x() << " " << pos.y() << " " << pos.z() << "\n";
            }
        }
    }

    outFile.close();
}