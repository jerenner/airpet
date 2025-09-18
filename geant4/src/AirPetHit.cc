#include "AirPetHit.hh"

#include "G4VVisManager.hh"
#include "G4VisAttributes.hh"
#include "G4Circle.hh"
#include "G4Colour.hh"
#include "G4UnitsTable.hh"
#include <iomanip>

G4ThreadLocal G4Allocator<AirPetHit>* AirPetHit::fAllocator = nullptr;

AirPetHit::AirPetHit()
  : G4VHit(),
    fTrackID(-1),
    fParentID(-1),
    fEdep(0.),
    fPos(0,0,0),
    fTime(0.),
    fParticleName(""),
    fVolumeName(""),
    fCopyNo(-1)
{}

AirPetHit::~AirPetHit() {}

AirPetHit::AirPetHit(const AirPetHit& right) : G4VHit()
{
  fTrackID = right.fTrackID;
  fParentID = right.fParentID;
  fEdep = right.fEdep;
  fPos = right.fPos;
  fTime = right.fTime;
  fParticleName = right.fParticleName;
  fVolumeName = right.fVolumeName;
  fCopyNo = right.fCopyNo;
}

const AirPetHit& AirPetHit::operator=(const AirPetHit& right)
{
  fTrackID = right.fTrackID;
  fParentID = right.fParentID;
  fEdep = right.fEdep;
  fPos = right.fPos;
  fTime = right.fTime;
  fParticleName = right.fParticleName;
  fVolumeName = right.fVolumeName;
  fCopyNo = right.fCopyNo;

  return *this;
}

int AirPetHit::operator==(const AirPetHit& right) const
{
  return (this == &right) ? 1 : 0;
}

void AirPetHit::Draw()
{
    G4VVisManager* pVVisManager = G4VVisManager::GetConcreteInstance();
    if(pVVisManager)
    {
        G4Circle circle(fPos);
        circle.SetScreenSize(4.); // in pixels
        circle.SetFillStyle(G4Circle::filled);
        G4Colour colour(1., 0., 0.); // Red
        G4VisAttributes attribs(colour);
        circle.SetVisAttributes(attribs);
        pVVisManager->Draw(circle);
    }
}

void AirPetHit::Print()
{
  G4cout << "  trackID: " << fTrackID << " particle: " << fParticleName
         << " parentID: " << fParentID
         << " volume: " << fVolumeName << "[" << fCopyNo << "]"
         << " Edep: " << std::setw(7) << G4BestUnit(fEdep,"Energy")
         << " Position: " << std::setw(7) << G4BestUnit(fPos,"Length")
         << " Time: " << std::setw(7) << G4BestUnit(fTime, "Time")
         << G4endl;
}
