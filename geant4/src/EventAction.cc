#include "EventAction.hh"
#include "AirPetHit.hh"
#include "AirPetTrajectory.hh"
#include "RunAction.hh"
#include "TrackingAction.hh"
#include "G4AnalysisManager.hh"
#include "G4Event.hh"
#include "G4HCofThisEvent.hh"
#include "G4HCtable.hh"
#include "G4RunManager.hh"
#include "G4SDManager.hh"
#include "G4TrajectoryContainer.hh"
#include "G4ios.hh"
#include "G4Tokenizer.hh"
#include "G4UIcommand.hh"
#include "G4UIdirectory.hh"
#include "G4UIparameter.hh"
#include <fstream>

EventAction::EventAction()
    : G4UserEventAction(), fTrackOutputDir("."), fStartEventToTrack(0),
      fEndEventToTrack(0) {
  fHitsCollectionIDs.push_back(-1);
  fG4petDir = new G4UIdirectory("/g4pet/");
  fEventDir = new G4UIdirectory("/g4pet/event/");
  fTrackOutputDirCmd = new G4UIcommand("/g4pet/event/printTracksToDir", this);
  fTrackOutputDirCmd->SetParameter(new G4UIparameter("dir", 's', false));
  fTrackOutputDirCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
  fSetTrackEventRangeCmd = new G4UIcommand("/g4pet/event/setTrackEventRange", this);
  fSetTrackEventRangeCmd->SetParameter(new G4UIparameter("startEvent", 'i', false));
  fSetTrackEventRangeCmd->SetParameter(new G4UIparameter("endEvent", 'i', false));
  fSetTrackEventRangeCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

EventAction::~EventAction() {}

void EventAction::SetNewValue(G4UIcommand *command, G4String newValue) {
  if (command == fTrackOutputDirCmd) {
    fTrackOutputDir = newValue;
  } else if (command == fSetTrackEventRangeCmd) {
    G4Tokenizer next(newValue);
    fStartEventToTrack = StoI(next());
    fEndEventToTrack = StoI(next());
  }
}

void EventAction::SetTrackEventRange(G4int start, G4int end) {
  fStartEventToTrack = start;
  fEndEventToTrack = end;
}

void EventAction::BeginOfEventAction(const G4Event * /*event*/) {}

void EventAction::EndOfEventAction(const G4Event *event) {
  auto analysisManager = G4AnalysisManager::Instance();
  auto runAction = static_cast<const RunAction *>(G4RunManager::GetRunManager()->GetUserRunAction());
  if (!runAction) return;

  if (runAction->GetSaveHits()) {
    G4int hits_ntuple_ID = runAction->GetSaveParticles() ? 1 : 0;
    if (fHitsCollectionIDs[0] == -1) {
      fHitsCollectionIDs.clear();
      G4SDManager *sdManager = G4SDManager::GetSDMpointer();
      G4HCtable *hcTable = sdManager->GetHCtable();
      for (G4int i = 0; i < hcTable->entries(); ++i) {
        G4int cID = sdManager->GetCollectionID(hcTable->GetHCname(i));
        if (cID >= 0) fHitsCollectionIDs.push_back(cID);
      }
    }
    G4HCofThisEvent *hce = event->GetHCofThisEvent();
    if (hce) {
      for (G4int cID : fHitsCollectionIDs) {
        auto hitsCollection = static_cast<AirPetHitsCollection *>(hce->GetHC(cID));
        if (hitsCollection) {
          for (size_t i = 0; i < hitsCollection->GetSize(); ++i) {
            auto hit = static_cast<AirPetHit *>(hitsCollection->GetHit(i));
            if (hit->GetEdep() < runAction->GetHitEnergyThreshold()) continue;
            analysisManager->FillNtupleIColumn(hits_ntuple_ID, 0, event->GetEventID());
            analysisManager->FillNtupleIColumn(hits_ntuple_ID, 1, hit->GetCopyNo());
            analysisManager->FillNtupleSColumn(hits_ntuple_ID, 2, hit->GetParticleName());
            analysisManager->FillNtupleIColumn(hits_ntuple_ID, 3, hit->GetTrackID());
            analysisManager->FillNtupleIColumn(hits_ntuple_ID, 4, hit->GetParentID());
            analysisManager->FillNtupleDColumn(hits_ntuple_ID, 5, hit->GetEdep());
            analysisManager->FillNtupleDColumn(hits_ntuple_ID, 6, hit->GetPosition().x());
            analysisManager->FillNtupleDColumn(hits_ntuple_ID, 7, hit->GetPosition().y());
            analysisManager->FillNtupleDColumn(hits_ntuple_ID, 8, hit->GetPosition().z());
            analysisManager->FillNtupleDColumn(hits_ntuple_ID, 9, hit->GetTime());
            analysisManager->AddNtupleRow(hits_ntuple_ID);
          }
        }
      }
    }
  }

  if (runAction->GetSaveParticles()) {
    G4TrajectoryContainer *trajectoryContainer = event->GetTrajectoryContainer();
    if (trajectoryContainer) {
      for (size_t i = 0; i < trajectoryContainer->size(); ++i) {
        auto traj = dynamic_cast<AirPetTrajectory *>((*trajectoryContainer)[i]);
        if (traj) {
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

  G4int eventID = event->GetEventID();
  if (eventID >= fStartEventToTrack && eventID <= fEndEventToTrack) {
    WriteTracksToFile(event);
  }
}

void EventAction::WriteTracksToFile(const G4Event *event) {
  G4TrajectoryContainer *trajectoryContainer = event->GetTrajectoryContainer();
  if (!trajectoryContainer) return;
  std::ostringstream filename;
  filename << fTrackOutputDir << "/event_" << std::setw(4) << std::setfill('0') << event->GetEventID() << "_tracks.txt";
  std::ofstream outFile(filename.str());
  if (!outFile.is_open()) return;
  outFile << "# EventID ParticleName TrackID ParentID PDGCode\n";
  for (size_t i = 0; i < trajectoryContainer->size(); ++i) {
    auto traj = dynamic_cast<AirPetTrajectory *>((*trajectoryContainer)[i]);
    if (traj) {
      outFile << "T " << event->GetEventID() << " " << traj->GetParticleName() << " " << traj->GetTrackID() << " " << traj->GetParentID() << " " << traj->GetPDGEncoding() << "\n";
      for (int j = 0; j < traj->GetPointEntries(); ++j) {
        G4VTrajectoryPoint *point = traj->GetPoint(j);
        const G4ThreeVector &pos = point->GetPosition();
        outFile << pos.x() << " " << pos.y() << " " << pos.z() << "\n";
      }
    }
  }
  outFile.close();
}
