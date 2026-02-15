#include "RunAction.hh"
#include "EventAction.hh"
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
  auto analysisManager = G4AnalysisManager::Instance();
  analysisManager->SetDefaultFileType("hdf5");
  analysisManager->SetVerboseLevel(1);
  fG4petDir = new G4UIdirectory("/g4pet/");
  fRunDir = new G4UIdirectory("/g4pet/run/");
  fSaveParticlesCmd = new G4UIcommand("/g4pet/run/saveParticles", this);
  fSaveParticlesCmd->SetParameter(new G4UIparameter("value", 'b', true));
  fSaveParticlesCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
  fSaveHitsCmd = new G4UIcommand("/g4pet/run/saveHits", this);
  fSaveHitsCmd->SetParameter(new G4UIparameter("value", 'b', true));
  fSaveHitsCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
  fHitEnergyThresholdCmd = new G4UIcmdWithADoubleAndUnit("/g4pet/run/hitEnergyThreshold", this);
  fHitEnergyThresholdCmd->SetParameterName("energy", true);
  fHitEnergyThresholdCmd->SetDefaultValue(0.0);
  fHitEnergyThresholdCmd->SetUnitCategory("Energy");
  fHitEnergyThresholdCmd->AvailableForStates(G4State_PreInit, G4State_Idle);
}

RunAction::~RunAction() {}

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
  auto analysisManager = G4AnalysisManager::Instance();
  G4cout << "--> RunAction::BeginOfRunAction: Opening output.hdf5" << G4endl;
  analysisManager->OpenFile("output.hdf5");
  if (fSaveParticles) {
    analysisManager->CreateNtuple("Tracks", "Particle Trajectories");
    analysisManager->CreateNtupleIColumn("EventID");
    analysisManager->CreateNtupleSColumn("ParticleName");
    analysisManager->CreateNtupleIColumn("TrackID");
    analysisManager->CreateNtupleIColumn("ParentID");
    analysisManager->CreateNtupleDColumn("Mass");
    analysisManager->CreateNtupleDColumn("InitialPosX");
    analysisManager->CreateNtupleDColumn("InitialPosY");
    analysisManager->CreateNtupleDColumn("InitialPosZ");
    analysisManager->CreateNtupleDColumn("InitialTime");
    analysisManager->CreateNtupleDColumn("FinalPosX");
    analysisManager->CreateNtupleDColumn("FinalPosY");
    analysisManager->CreateNtupleDColumn("FinalPosZ");
    analysisManager->CreateNtupleDColumn("FinalTime");
    analysisManager->CreateNtupleDColumn("InitialMomX");
    analysisManager->CreateNtupleDColumn("InitialMomY");
    analysisManager->CreateNtupleDColumn("InitialMomZ");
    analysisManager->CreateNtupleDColumn("FinalMomX");
    analysisManager->CreateNtupleDColumn("FinalMomY");
    analysisManager->CreateNtupleDColumn("FinalMomZ");
    analysisManager->CreateNtupleSColumn("InitialVolume");
    analysisManager->CreateNtupleSColumn("FinalVolume");
    analysisManager->CreateNtupleSColumn("CreatorProcess");
    analysisManager->FinishNtuple(0);
  }
  if (fSaveHits) {
    G4int hits_ntuple_ID = fSaveParticles ? 1 : 0;
    analysisManager->CreateNtuple("Hits", "Sensitive Detector Hits");
    analysisManager->CreateNtupleIColumn("EventID");
    analysisManager->CreateNtupleIColumn("CopyNo");
    analysisManager->CreateNtupleSColumn("ParticleName");
    analysisManager->CreateNtupleIColumn("TrackID");
    analysisManager->CreateNtupleIColumn("ParentID");
    analysisManager->CreateNtupleDColumn("Edep");
    analysisManager->CreateNtupleDColumn("PosX");
    analysisManager->CreateNtupleDColumn("PosY");
    analysisManager->CreateNtupleDColumn("PosZ");
    analysisManager->CreateNtupleDColumn("Time");
    analysisManager->FinishNtuple(hits_ntuple_ID);
  }
}

void RunAction::EndOfRunAction(const G4Run * /*aRun*/) {
  auto analysisManager = G4AnalysisManager::Instance();
  G4cout << "--> RunAction::EndOfRunAction: Writing and Closing..." << G4endl;
  analysisManager->Write();
  analysisManager->CloseFile();
}
